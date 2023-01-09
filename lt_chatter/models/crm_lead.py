##############################################################################
# Copyright (c) 2022 lumitec GmbH (https://www.lumitec.solutions)
# All Right Reserved
#
# See LICENSE file for full licensing details.
##############################################################################

from odoo import fields, models


class Lead(models.Model):
    _inherit = 'crm.lead'

    send_mail = fields.Boolean(string='Send email', default=False)
