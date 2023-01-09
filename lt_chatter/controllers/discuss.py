##############################################################################
# Copyright (c) 2022 lumitec GmbH (https://www.lumitec.solutions)
# All Right Reserved
#
# See LICENSE file for full licensing details.
##############################################################################

from odoo.addons.mail.controllers.discuss import DiscussController


class ChatterDiscussController(DiscussController):

    def _get_allowed_message_post_params(self):
        return {'attachment_ids', 'body', 'message_type', 'partner_ids', 'subtype_xmlid', 'parent_id', 'checkbox'}
