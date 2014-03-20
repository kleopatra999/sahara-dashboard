# Copyright (c) 2013 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from horizon import forms
import logging

from django.utils.translation import ugettext as _

from horizon import exceptions
from horizon import workflows

from saharaclient.api import base as api_base
from saharadashboard.api import client as saharaclient
from saharadashboard.utils import importutils

import saharadashboard.api.helpers as helpers
import saharadashboard.utils.workflow_helpers as whelpers


# horizon.api is for backward compatibility with folsom
nova = importutils.import_any('openstack_dashboard.api.nova',
                              'horizon.api.nova')

network = importutils.import_any('openstack_dashboard.api.network',
                                 'horizon.api.network')

LOG = logging.getLogger(__name__)


class GeneralConfigAction(workflows.Action):
    nodegroup_name = forms.CharField(label=_("Template Name"),
                                     required=True)

    description = forms.CharField(label=_("Description"),
                                  required=False,
                                  widget=forms.Textarea)

    flavor = forms.ChoiceField(label=_("OpenStack Flavor"),
                               required=True)

    storage = forms.ChoiceField(
        label=_("Storage location"),
        required=True,
        help_text=_("Storage"),
        choices=[("ephemeral_drive", "Ephemeral Drive"),
                 ("cinder_volume", "Cinder Volume")],
        widget=forms.Select(attrs={"class": "storage_field"}))

    volumes_per_node = forms.IntegerField(
        label=_("Volumes per node"),
        required=False,
        initial=1,
        widget=forms.TextInput(attrs={"class": "volume_per_node_field"})
    )

    volumes_size = forms.IntegerField(
        label=_("Volumes size (GB)"),
        required=False,
        initial=10,
        widget=forms.TextInput(attrs={"class": "volume_size_field"})
    )

    hidden_configure_field = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"class": "hidden_configure_field"}))

    def __init__(self, request, *args, **kwargs):
        super(GeneralConfigAction, self).__init__(request, *args, **kwargs)

        sahara = saharaclient.client(request)
        hlps = helpers.Helpers(sahara)

        plugin, hadoop_version = whelpers.\
            get_plugin_and_hadoop_version(request)
        process_choices = []
        version_details = sahara.plugins.get_version_details(plugin,
                                                             hadoop_version)

        for service, processes in version_details.node_processes.items():
            for process in processes:
                process_choices.append(
                    (str(service) + ":" + str(process), process))

        if not saharaclient.AUTO_ASSIGNMENT_ENABLED:
            pools = network.floating_ip_pools_list(request)
            pool_choices = [(pool.id, pool.name) for pool in pools]
            pool_choices.insert(0, (None, "Do not assign floating IPs"))

            self.fields['floating_ip_pool'] = forms.ChoiceField(
                label=_("Floating IP pool"),
                choices=pool_choices,
                required=False)

        self.fields["processes"] = forms.MultipleChoiceField(
            label=_("Processes"),
            required=True,
            widget=forms.CheckboxSelectMultiple(),
            help_text=_("Processes to be launched in node group"),
            choices=process_choices)

        self.fields["plugin_name"] = forms.CharField(
            widget=forms.HiddenInput(),
            initial=plugin
        )
        self.fields["hadoop_version"] = forms.CharField(
            widget=forms.HiddenInput(),
            initial=hadoop_version
        )

        node_parameters = hlps.get_general_node_group_configs(plugin,
                                                              hadoop_version)
        for param in node_parameters:
            self.fields[param.name] = whelpers.build_control(param)

    def populate_flavor_choices(self, request, context):
        try:
            flavors = nova.flavor_list(request)
            flavor_list = [(flavor.id, "%s" % flavor.name)
                           for flavor in flavors]
        except Exception:
            flavor_list = []
            exceptions.handle(request,
                              _('Unable to retrieve instance flavors.'))
        return sorted(flavor_list)

    def get_help_text(self):
        extra = dict()
        plugin, hadoop_version = whelpers.\
            get_plugin_and_hadoop_version(self.request)
        extra["plugin_name"] = plugin
        extra["hadoop_version"] = hadoop_version
        return super(GeneralConfigAction, self).get_help_text(extra)

    class Meta:
        name = _("Configure Node Group Template")
        help_text_template = \
            ("nodegroup_templates/_configure_general_help.html")


class GeneralConfig(workflows.Step):
    action_class = GeneralConfigAction
    contributes = ("general_nodegroup_name", )

    def contribute(self, data, context):
        for k, v in data.items():
            if "hidden" in k:
                continue
            context["general_" + k] = v if v != "None" else None

        post = self.workflow.request.POST
        context['general_processes'] = post.getlist("processes")
        return context


class ConfigureNodegroupTemplate(whelpers.ServiceParametersWorkflow,
                                 whelpers.StatusFormatMixin):
    slug = "configure_nodegroup_template"
    name = _("Create Node Group Template")
    finalize_button_name = _("Create")
    success_message = _("Created Node Group Template %s")
    name_property = "general_nodegroup_name"
    success_url = "horizon:sahara:nodegroup_templates:index"
    default_steps = (GeneralConfig,)

    def __init__(self, request, context_seed, entry_point, *args, **kwargs):
        sahara = saharaclient.client(request)
        hlps = helpers.Helpers(sahara)

        plugin, hadoop_version = whelpers.\
            get_plugin_and_hadoop_version(request)

        general_parameters = hlps.get_general_node_group_configs(
            plugin,
            hadoop_version)
        service_parameters = hlps.get_targeted_node_group_configs(
            plugin,
            hadoop_version)

        self._populate_tabs(general_parameters, service_parameters)

        super(ConfigureNodegroupTemplate, self).__init__(request,
                                                         context_seed,
                                                         entry_point,
                                                         *args, **kwargs)

    def is_valid(self):
        missing = self.depends_on - set(self.context.keys())
        if missing:
            raise exceptions.WorkflowValidationError(
                "Unable to complete the workflow. The values %s are "
                "required but not present." % ", ".join(missing))
        checked_steps = []

        if "general_processes" in self.context:
            checked_steps = self.context["general_processes"]
        enabled_services = set([])
        for process_name in checked_steps:
            enabled_services.add(str(process_name).split(":")[0])

        steps_valid = True
        for step in self.steps:
            process_name = str(getattr(step, "process_name", None))
            if process_name not in enabled_services and \
                    not isinstance(step, GeneralConfig):
                continue
            if not step.action.is_valid():
                steps_valid = False
                step.has_errors = True
        if not steps_valid:
            return steps_valid
        return self.validate(self.context)

    def handle(self, request, context):
        try:
            sahara = saharaclient.client(request)

            processes = []
            for service_process in context["general_processes"]:
                processes.append(str(service_process).split(":")[1])

            configs_dict = whelpers.parse_configs_from_context(context,
                                                               self.defaults)

            plugin, hadoop_version = whelpers.\
                get_plugin_and_hadoop_version(request)

            volumes_per_node = None
            volumes_size = None

            if context["general_storage"] == "cinder_volume":
                volumes_per_node = context["general_volumes_per_node"]
                volumes_size = context["general_volumes_size"]

            sahara.node_group_templates.create(
                name=context["general_nodegroup_name"],
                plugin_name=plugin,
                hadoop_version=hadoop_version,
                description=context["general_description"],
                flavor_id=context["general_flavor"],
                volumes_per_node=volumes_per_node,
                volumes_size=volumes_size,
                node_processes=processes,
                node_configs=configs_dict,
                floating_ip_pool=context.get("general_floating_ip_pool", None))
            return True
        except api_base.APIException as e:
            self.error_description = str(e)
            return False
        except Exception:
            exceptions.handle(request)


class SelectPluginAction(workflows.Action,
                         whelpers.PluginAndVersionMixin):
    hidden_create_field = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"class": "hidden_create_field"}))

    def __init__(self, request, *args, **kwargs):
        super(SelectPluginAction, self).__init__(request, *args, **kwargs)

        sahara = saharaclient.client(request)
        self._generate_plugin_version_fields(sahara)

    class Meta:
        name = _("Select plugin and hadoop version")
        help_text_template = ("nodegroup_templates/_create_general_help.html")


class SelectPlugin(workflows.Step):
    action_class = SelectPluginAction
    contributes = ("plugin_name", "hadoop_version")

    def contribute(self, data, context):
        context = super(SelectPlugin, self).contribute(data, context)
        context["plugin_name"] = data.get('plugin_name', None)
        context["hadoop_version"] = \
            data.get(context["plugin_name"] + "_version", None)
        return context


class CreateNodegroupTemplate(workflows.Workflow):
    slug = "create_nodegroup_template"
    name = _("Create Node Group Template")
    finalize_button_name = _("Create")
    success_message = _("Created")
    failure_message = _("Could not create")
    success_url = "horizon:sahara:nodegroup_templates:index"
    default_steps = (SelectPlugin,)
