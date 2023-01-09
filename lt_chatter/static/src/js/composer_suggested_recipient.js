odoo.define('lt_chatter.mail_non_contact', function (require) {
"use strict";
const { ComposerSuggestedRecipient } = require("@mail/components/composer_suggested_recipient/composer_suggested_recipient")
const { Component } = owl;
const { patch } = require('web.utils');

patch(ComposerSuggestedRecipient.prototype, 'ComposerSuggestedRecipientEmail',{

    _onChangeCheckbox() {
            const isChecked = this._checkboxRef.el.checked;
            this.suggestedRecipientInfo.update({ isSelected: isChecked });
    }
})
})
