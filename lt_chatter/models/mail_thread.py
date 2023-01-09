##############################################################################
# Copyright (c) 2022 lumitec GmbH (https://www.lumitec.solutions)
# All Right Reserved
#
# See LICENSE file for full licensing details.
##############################################################################
from odoo import fields, models, registry, Command, SUPERUSER_ID, api, _
from odoo.tools.misc import clean_context, split_every
import threading
import logging
_logger = logging.getLogger(__name__)



class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, *,
                     body='', subject=None, message_type='notification',
                     email_from=None, author_id=None, parent_id=False,
                     subtype_xmlid=None, subtype_id=False, partner_ids=None, checkbox=False,
                     attachments=None, attachment_ids=None,
                     add_sign=True, record_name=False,
                     **kwargs):
        """ Post a new message in an existing thread, returning the new
            mail.message ID.
            :param str body: body of the message, usually raw HTML that will
                be sanitized
            :param str subject: subject of the message
            :param str message_type: see mail_message.message_type field. Can be anything but
                user_notification, reserved for message_notify
            :param int parent_id: handle thread formation
            :param int subtype_id: subtype_id of the message, used mainly use for
                followers notification mechanism;
            :param list(int) partner_ids: partner_ids to notify in addition to partners
                computed based on subtype / followers matching;
            :param list(tuple(str,str), tuple(str,str, dict) or int) attachments : list of attachment tuples in the form
                ``(name,content)`` or ``(name,content, info)``, where content is NOT base64 encoded
            :param list id attachment_ids: list of existing attachement to link to this message
                -Should only be setted by chatter
                -Attachement object attached to mail.compose.message(0) will be attached
                    to the related document.
            Extra keyword arguments will be used as default column values for the
            new mail.message record.
            :return int: ID of newly created mail.message
        """
        self.ensure_one()  # should always be posted on a record, use message_notify if no record
        # split message additional values from notify additional values
        msg_kwargs = dict((key, val) for key, val in kwargs.items() if key in self.env['mail.message']._fields)
        notif_kwargs = dict((key, val) for key, val in kwargs.items() if key not in msg_kwargs)

        # preliminary value safety check
        partner_ids = set(partner_ids or [])
        if self._name == 'mail.thread' or not self.id or message_type == 'user_notification':
            raise ValueError(
                _('Posting a message should be done on a business document. Use message_notify to send a notification to an user.'))
        if 'channel_ids' in kwargs:
            raise ValueError(
                _("Posting a message with channels as listeners is not supported since Odoo 14.3+. Please update code accordingly."))
        if 'model' in msg_kwargs or 'res_id' in msg_kwargs:
            raise ValueError(
                _("message_post does not support model and res_id parameters anymore. Please call message_post on record."))
        if 'subtype' in kwargs:
            raise ValueError(
                _("message_post does not support subtype parameter anymore. Please give a valid subtype_id or subtype_xmlid value instead."))
        if any(not isinstance(pc_id, int) for pc_id in partner_ids):
            raise ValueError(_('message_post partner_ids and must be integer list, not commands.'))

        self = self._fallback_lang()  # add lang to context imediatly since it will be usefull in various flows latter.

        # Explicit access rights check, because display_name is computed as sudo.
        self.check_access_rights('read')
        self.check_access_rule('read')
        record_name = record_name or self.display_name

        # Find the message's author
        if self.env.user._is_public() and 'guest' in self.env.context:
            author_guest_id = self.env.context['guest'].id
            author_id, email_from = False, False
        else:
            author_guest_id = False
            author_id, email_from = self._message_compute_author(author_id, email_from, raise_exception=True)

        if subtype_xmlid:
            subtype_id = self.env['ir.model.data']._xmlid_to_res_id(subtype_xmlid)
        if not subtype_id:
            subtype_id = self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note')

        # automatically subscribe recipients if asked to
        if self._context.get('mail_post_autofollow') and partner_ids:
            self.message_subscribe(partner_ids=list(partner_ids))

        values = dict(msg_kwargs)
        values.update({
            'author_id': author_id,
            'author_guest_id': author_guest_id,
            'email_from': email_from,
            'model': self._name,
            'res_id': self.id,
            'body': body,
            'subject': subject or False,
            'message_type': message_type,
            'parent_id': self._message_compute_parent_id(parent_id),
            'subtype_id': subtype_id,
            'partner_ids': partner_ids,
            'add_sign': add_sign,
            'record_name': record_name,
            'checkbox': checkbox,
        })
        attachments = attachments or []
        attachment_ids = attachment_ids or []
        attachement_values = self._message_post_process_attachments(attachments, attachment_ids, values)
        values.update(attachement_values)  # attachement_ids, [body]

        new_message = self._message_create(values)

        # Set main attachment field if necessary
        self._message_set_main_attachment_id(values['attachment_ids'])

        if values['author_id'] and values['message_type'] != 'notification' and not self._context.get(
                'mail_create_nosubscribe'):
            if self.env['res.partner'].browse(
                    values['author_id']).active:  # we dont want to add odoobot/inactive as a follower
                self._message_subscribe(partner_ids=[values['author_id']])

        self._message_post_after_hook(new_message, values)
        self._notify_thread(new_message, values, **notif_kwargs)
        return new_message

    def _notify_thread(self, message, msg_vals=False, notify_by_email=True, **kwargs):
        """ Main notification method. This method basically does two things

         * call ``_notify_compute_recipients`` that computes recipients to
           notify based on message record or message creation values if given
           (to optimize performance if we already have data computed);
         * performs the notification process by calling the various notification
           methods implemented;

        :param message: mail.message record to notify;
        :param msg_vals: dictionary of values used to create the message. If given
          it is used instead of accessing ``self`` to lessen query count in some
          simple cases where no notification is actually required;

        Kwargs allow to pass various parameters that are given to sub notification
        methods. See those methods for more details about the additional parameters.
        Parameters used for email-style notifications
        """
        msg_vals = msg_vals if msg_vals else {}
        rdata = self._notify_compute_recipients(message, msg_vals)

        self._notify_record_by_inbox(message, rdata, msg_vals=msg_vals, **kwargs)
        if notify_by_email:
            self._notify_record_by_email(message, rdata, msg_vals=msg_vals, **kwargs)

        return rdata

    def _notify_record_by_email(self, message, recipients_data, msg_vals=False,
                                model_description=False, mail_auto_delete=True, check_existing=False,
                                force_send=True, send_after_commit=True,
                                **kwargs):
        """ Method to send email linked to notified messages.

        :param message: mail.message record to notify;
        :param recipients_data: see ``_notify_thread``;
        :param msg_vals: see ``_notify_thread``;

        :param model_description: model description used in email notification process
          (computed if not given);
        :param mail_auto_delete: delete notification emails once sent;
        :param check_existing: check for existing notifications to update based on
          mailed recipient, otherwise create new notifications;

        :param force_send: send emails directly instead of using queue;
        :param send_after_commit: if force_send, tells whether to send emails after
          the transaction has been committed using a post-commit hook;
        """
        partners_data = [r for r in recipients_data if r['notif'] == 'email']
        # if not partners_data:
        #     return True

        model = msg_vals.get('model') if msg_vals else message.model
        model_name = model_description or (self._fallback_lang().env['ir.model']._get(
            model).display_name if model else False)  # one query for display name
        recipients_groups_data = self._notify_classify_recipients(partners_data, model_name, msg_vals=msg_vals)
        force_send = self.env.context.get('mail_notify_force_send', force_send)

        template_values = self._notify_prepare_template_context(message, msg_vals,
                                                                model_description=model_description)  # 10 queries

        email_layout_xmlid = msg_vals.get('email_layout_xmlid') if msg_vals else message.email_layout_xmlid
        template_xmlid = email_layout_xmlid if email_layout_xmlid else 'mail.message_notification_email'
        try:
            base_template = self.env.ref(template_xmlid, raise_if_not_found=True).with_context(
                lang=template_values['lang'])  # 1 query
        except ValueError:
            _logger.warning(
                'QWeb template %s not found when sending notification emails. Sending without layouting.' % (
                    template_xmlid))
            base_template = False

        mail_subject = message.subject or (
                    message.record_name and 'Re: %s' % message.record_name)  # in cache, no queries
        # Replace new lines by spaces to conform to email headers requirements
        mail_subject = ' '.join((mail_subject or '').splitlines())
        # compute references: set references to the parent and add current message just to
        # have a fallback in case replies mess with Messsage-Id in the In-Reply-To (e.g. amazon
        # SES SMTP may replace Message-Id and In-Reply-To refers an internal ID not stored in Odoo)
        message_sudo = message.sudo()
        if message_sudo.parent_id:
            references = f'{message_sudo.parent_id.message_id} {message_sudo.message_id}'
        else:
            references = message_sudo.message_id
        # prepare notification mail values
        base_mail_values = {
            'mail_message_id': message.id,
            'mail_server_id': message.mail_server_id.id,
            # 2 query, check acces + read, may be useless, Falsy, when will it be used?
            'auto_delete': mail_auto_delete,
            # due to ir.rule, user have no right to access parent message if message is not published
            'references': references,
            'subject': mail_subject,
        }
        base_mail_values = self._notify_by_email_add_values(base_mail_values)
        SafeMail = self.env['mail.mail'].sudo().with_context(clean_context(self._context))
        SafeNotification = self.env['mail.notification'].sudo().with_context(clean_context(self._context))
        emails = self.env['mail.mail'].sudo()
        lead = self.env['crm.lead'].browse(msg_vals.get('res_id'))
        notif_create_values = []
        if lead:
            if lead.email_from and not partners_data and (msg_vals.get('checkbox') == True):
                mail_body = self.env['mail.render.mixin']._replace_local_links(message.body)
                create_values = {
                    'body_html': mail_body,
                    'subject': mail_subject,
                    'email_to': lead.email_from,
                    'message_type': 'comment',
                    'is_notification': True
                }
                create_values.update(base_mail_values)
                email = SafeMail.create(create_values)
                if email:
                    partner = self.env.ref('lt_chatter.res_partner_contact')
                    if partner.email == '':
                        partner.update({
                            'email': lead.email_from
                        })

                    notif_create_values += [{
                        'mail_message_id': message.id,
                        'res_partner_id': partner.id,
                        'notification_type': 'email',
                        'mail_mail_id': email.id,
                        'is_read': True,  # discard Inbox notification
                        'notification_status': 'ready',
                    }]
                    partner = self.env.ref('lt_chatter.res_partner_contact')
                    if partner.email != False:
                        partner.update({
                            'email': ''
                        })
                emails |= email
            if kwargs.get('email_to'):
                mail_body = self.env['mail.render.mixin']._replace_local_links(message.body)
                create_values = {
                    'body_html': mail_body,
                    'subject': mail_subject,
                    'email_to': kwargs.get('email_to'),
                    'message_type': 'comment',
                    'is_notification': True
                }
                email = SafeMail.create(create_values)
                partner = self.env.ref('lt_chatter.res_partner_contact')
                if partner.email == '':
                    partner.update({
                        'email': lead.email_from
                    })
                notif_create_values += [{
                    'mail_message_id': message.id,
                    'res_partner_id': partner.id,
                    'notification_type': 'email',
                    'mail_mail_id': email.id,
                    'is_read': True,  # discard Inbox notification
                    'notification_status': 'ready',
                }]
                partner = self.env.ref('lt_chatter.res_partner_contact')
                if partner.email != False:
                    partner.update({
                        'email': ''
                    })

                emails |= email

        # loop on groups (customer, portal, user,  ... + model specific like group_sale_salesman)
        recipients_max = 50
        for recipients_group_data in recipients_groups_data:
            # generate notification email content
            recipients_ids = recipients_group_data.pop('recipients')
            render_values = {**template_values, **recipients_group_data}
            # {company, is_discussion, lang, message, model_description, record, record_name, signature, subtype, tracking_values, website_url}
            # {actions, button_access, has_button_access, recipients}

            if base_template:
                mail_body = base_template._render(render_values, engine='ir.qweb', minimal_qcontext=True)
            else:
                mail_body = message.body
            mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)

            # create email
            for recipients_ids_chunk in split_every(recipients_max, recipients_ids):
                recipient_values = self._notify_email_recipient_values(recipients_ids_chunk)
                email_to = recipient_values['email_to']
                recipient_ids = recipient_values['recipient_ids']

                create_values = {
                    'body_html': mail_body,
                    'subject': mail_subject,
                    'recipient_ids': [Command.link(pid) for pid in recipient_ids],
                }
                if email_to:
                    create_values['email_to'] = email_to
                create_values.update(
                    base_mail_values)  # mail_message_id, mail_server_id, auto_delete, references, headers
                email = SafeMail.create(create_values)

                if email and recipient_ids:
                    tocreate_recipient_ids = list(recipient_ids)
                    if check_existing:
                        existing_notifications = self.env['mail.notification'].sudo().search([
                            ('mail_message_id', '=', message.id),
                            ('notification_type', '=', 'email'),
                            ('res_partner_id', 'in', tocreate_recipient_ids)
                        ])
                        if existing_notifications:
                            tocreate_recipient_ids = [rid for rid in recipient_ids if
                                                      rid not in existing_notifications.mapped('res_partner_id.id')]
                            existing_notifications.write({
                                'notification_status': 'ready',
                                'mail_mail_id': email.id,
                            })
                    notif_create_values += [{
                        'mail_message_id': message.id,
                        'res_partner_id': recipient_id,
                        'notification_type': 'email',
                        'mail_mail_id': email.id,
                        'is_read': True,  # discard Inbox notification
                        'notification_status': 'ready',
                    } for recipient_id in tocreate_recipient_ids]
                emails |= email

        if notif_create_values:
            SafeNotification.create(notif_create_values)

        # NOTE:
        #   1. for more than 50 followers, use the queue system
        #   2. do not send emails immediately if the registry is not loaded,
        #      to prevent sending email during a simple update of the database
        #      using the command-line.
        test_mode = getattr(threading.current_thread(), 'testing', False)
        if force_send and len(emails) < recipients_max and (not self.pool._init or test_mode):
            # unless asked specifically, send emails after the transaction to
            # avoid side effects due to emails being sent while the transaction fails
            if not test_mode and send_after_commit:
                email_ids = emails.ids
                dbname = self.env.cr.dbname
                _context = self._context

                @self.env.cr.postcommit.add
                def send_notifications():
                    db_registry = registry(dbname)
                    with db_registry.cursor() as cr:
                        env = api.Environment(cr, SUPERUSER_ID, _context)
                        env['mail.mail'].browse(email_ids).send()
            else:
                emails.send()

        return True
