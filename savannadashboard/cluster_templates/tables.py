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

import logging

from django.core import urlresolvers
from django import template
from django.utils import http
from django.utils.translation import ugettext_lazy as _

from horizon import tables

from savannadashboard.api.client import client as savannaclient

LOG = logging.getLogger(__name__)


def render_node_groups(cluster_template):
    template_name = 'cluster_templates/_nodegroups_list.html'
    context = {"node_groups": cluster_template.node_groups}
    return template.loader.render_to_string(template_name, context)


class UploadFile(tables.LinkAction):
    name = 'upload_file'
    verbose_name = _("Upload Template")
    url = 'horizon:savanna:cluster_templates:upload_file'
    classes = ("btn-launch", "ajax-modal")


class CreateCluster(tables.LinkAction):
    name = "create cluster"
    verbose_name = _("Launch Cluster")
    url = "horizon:savanna:clusters:configure-cluster"
    classes = ("btn-launch", "ajax-modal")

    def get_link_url(self, datum):
        base_url = urlresolvers.reverse(self.url)

        params = http.urlencode({"hadoop_version": datum.hadoop_version,
                                 "plugin_name": datum.plugin_name,
                                 "cluster_template_id": datum.id})
        return "?".join([base_url, params])


class CopyTemplate(tables.LinkAction):
    name = "copy"
    verbose_name = _("Copy Template")
    url = "horizon:savanna:cluster_templates:copy"
    classes = ("ajax-modal", )


class DeleteTemplate(tables.BatchAction):
    name = "delete_cluster_template"
    verbose_name = _("Delete Template")
    classes = ("btn-terminate", "btn-danger")

    action_present = _("Delete")
    action_past = _("Deleted")
    data_type_singular = _("Template")
    data_type_plural = _("Templates")

    def allowed(self, request, template):
        return True

    def action(self, request, template_id):
        savanna = savannaclient(request)
        savanna.cluster_templates.delete(template_id)


class CreateClusterTemplate(tables.LinkAction):
    name = "create"
    verbose_name = _("Create Template")
    url = "horizon:savanna:cluster_templates:create-cluster-template"
    classes = ("ajax-modal", "btn-create", "create-clustertemplate-btn")


class ConfigureClusterTemplate(tables.LinkAction):
    name = "configure"
    verbose_name = _("Configure Cluster Template")
    url = "horizon:savanna:cluster_templates:configure-cluster-template"
    classes = ("ajax-modal", "btn-create", "configure-clustertemplate-btn")
    attrs = {"style": "display: none"}


class ClusterTemplatesTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"),
                         link=("horizon:savanna:cluster_templates:details"))
    plugin_name = tables.Column("plugin_name",
                                verbose_name=_("Plugin"))
    hadoop_version = tables.Column("hadoop_version",
                                   verbose_name=_("Hadoop Version"))
    node_groups = tables.Column(render_node_groups,
                                verbose_name=_("Node Groups"))
    description = tables.Column("description",
                                verbose_name=_("Description"))

    class Meta:
        name = "cluster_templates"
        verbose_name = _("Cluster Templates")
        table_actions = (UploadFile,
                         CreateClusterTemplate,
                         ConfigureClusterTemplate,
                         DeleteTemplate,)

        row_actions = (CreateCluster,
                       CopyTemplate,
                       DeleteTemplate,)
