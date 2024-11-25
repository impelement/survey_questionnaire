{
    'name': 'Questionnaires',
    'version': '17.0.0.1',
    'author': "Impelement Digital",
    'depends': [
        'base',
        'portal',
        'survey',
        'mail',
        'project',

        ],
    'data': [
            'data/mail_template_data.xml',
            'security/security.xml',
            'security/ir.model.access.csv',
            'views/views.xml',
            'views/survey_template.xml',
    ], 
    'installable': True,
    'auto_install': False,
}

