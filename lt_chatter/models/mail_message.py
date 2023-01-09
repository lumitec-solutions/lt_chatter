##############################################################################
# Copyright (c) 2022 lumitec GmbH (https://www.lumitec.solutions)
# All Right Reserved
#
# See LICENSE file for full licensing details.
##############################################################################

from odoo import fields, models


class MailMessage(models.Model):
    _inherit = "mail.message"

    checkbox = fields.Boolean(string="Checkbox", default=False)


class MailComposer(models.TransientModel):
    _inherit = "mail.compose.message"

    email_to = fields.Char(string="Email To")
    is_partner = fields.Boolean(string="Is Partner", default=False)
