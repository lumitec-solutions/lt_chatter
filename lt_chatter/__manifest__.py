##############################################################################
# Copyright (c) 2022 lumitec GmbH (https://www.lumitec.solutions)
# All Right Reserved
#
# See LICENSE file for full licensing details.
##############################################################################
{
    'name': 'lumitec Chatter',
    'summary': 'Send Message Lead should not create a Contact',
    'author': "lumitec GmbH",
    'website': "https://www.lumitec.solutions",
    'category': '',
    'version': '15.0.1.0.0',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'crm',
    ],
    'data': [
        'data/contact.xml',
        'views/mail_message.xml',
        'views/mail_compose_message.xml',
    ],
    "assets": {
        "web.assets_backend": [
            'lt_chatter/static/src/js/composer_suggested_recipient.js',
            'lt_chatter/static/src/js/composer_view.js'
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
