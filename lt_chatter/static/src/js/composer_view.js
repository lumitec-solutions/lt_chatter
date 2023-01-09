odoo.define('lt_chatter.composer_post', function (require) {
"use strict";
const { registerNewModel,registerInstancePatchModel } = require('@mail/model/model_core')
const { addLink, escapeAndCompactTextContent, parseAndTransform } = require('@mail/js/utils')

registerInstancePatchModel('mail.composer_view', 'mail/static/src/models/composer_view/composer_view.js',{
     _getMessageData() {
            const escapedAndCompactContent = escapeAndCompactTextContent(this.composer.textInputContent);
            let body = escapedAndCompactContent.replace(/&nbsp;/g, ' ').trim();
            // This message will be received from the mail composer as html content
            // subtype but the urls will not be linkified. If the mail composer
            // takes the responsibility to linkify the urls we end up with double
            // linkification a bit everywhere. Ideally we want to keep the content
            // as text internally and only make html enrichment at display time but
            // the current design makes this quite hard to do.
            body = this._generateMentionsLinks(body);
            body = parseAndTransform(body, addLink);
            body = this._generateEmojisOnHtml(body);
            if ($('.custom-control-input')[0]) {
                var checkbox= $('.custom-control-input')[0].checked
                return {
                    attachment_ids: this.composer.attachments.map(attachment => attachment.id),
                    body,
                    message_type: 'comment',
                    partner_ids: this.composer.recipients.map(partner => partner.id),
                    checkbox
                };
            }
            else {
                return {
                    attachment_ids: this.composer.attachments.map(attachment => attachment.id),
                    body,
                    message_type: 'comment',
                    partner_ids: this.composer.recipients.map(partner => partner.id),
                };
            }
        },
        async openFullComposer() {
            const attachmentIds = this.composer.attachments.map(attachment => attachment.id);
            var email_to = ''
            if ($('.custom-control-input')[0]){
                if ((this.composer.recipients.map(partner => partner.id).length > 0) && ($('.custom-control-input')[0].checked === true)){
                      var is_partner = true;
                }
                else if ((this.composer.recipients.map(partner => partner.id).length === 0) && ($('.custom-control-input')[0].checked === true)) {
                      var is_partner = false;
                      var email_to = $('.custom-control-input')[0].nextElementSibling.innerHTML.split(' ')[0];
                }
            }
            else{
                var is_partner = true;
            }
            const context = {
                    default_attachment_ids: attachmentIds,
                    default_body: escapeAndCompactTextContent(this.composer.textInputContent),
                    default_is_log: this.composer.isLog,
                    default_model: this.composer.activeThread.model,
                    default_partner_ids: this.composer.recipients.map(partner => partner.id),
                    default_res_id: this.composer.activeThread.id,
                    mail_post_autofollow: true,
                    default_is_partner: is_partner,
                    default_email_to: email_to

                  };

            const action = {
                type: 'ir.actions.act_window',
                res_model: 'mail.compose.message',
                view_mode: 'form',
                views: [[false, 'form']],
                target: 'new',
                context: context,
            };
            const composer = this.composer;
            const options = {
                on_close: () => {
                    if (!composer.exists()) {
                        return;
                    }
                    composer._reset();
                    if (composer.activeThread) {
                        composer.activeThread.loadNewMessages();
                    }
                },
            };
            await this.env.bus.trigger('do-action', { action, options });
        }
})

})