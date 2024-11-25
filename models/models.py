from odoo import models, fields, api, _
import werkzeug
import logging
_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from odoo.exceptions import UserError

class UserInput(models.Model):
    _inherit  = 'survey.user_input'

    project_id = fields.Many2one('project.project',string="Project")

class ProjSurvey(models.Model):
    _name  = 'proj.survey'

    project_id = fields.Many2one("project.project")
    survey_id = fields.Many2one("survey.survey")

class SurveyInvite(models.TransientModel):
    _inherit = 'survey.invite'

    survey_ids = fields.Many2many('survey.survey', string='Surveys')
    partner_ids = fields.Many2many('res.partner', 'survey_invite_partner_ids', 'invite_id', 'partner_id', string='Collaborators', readonly=False)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)
    email_subject = fields.Char("Email Subject")
    survey_id = fields.Many2one('survey.survey', string='Survey', required=False)

    @api.onchange('survey_ids')
    def _onchange_survey_ids(self):
        """Automatically set survey_id to the first selected survey from survey_ids."""
        if self.survey_ids:
            self.survey_id = self.survey_ids[0]  # Set survey_id to the first selected survey
        else:
            self.survey_id = False  # Clear survey_id if no surveys are selected

    def action_invite(self):
        self.ensure_one()
        Partner = self.env['res.partner']

        valid_partners = self.partner_ids
        valid_emails = [partner.email for partner in valid_partners if partner.email]

        if not valid_partners and not valid_emails:
            raise UserError(_("Please enter at least one valid recipient."))

        for survey in self.survey_ids:
            # Prepare answers for the specific survey
            answers = self._prepare_answers(valid_partners, valid_emails, survey)
            for answer in answers:
                # Set the subject for the current survey
                self.survey_id = survey
                self._set_subject(survey)
                self._send_mail(answer)

        return {'type': 'ir.actions.act_window_close'}

    def _prepare_answers(self, partners, emails, surveys):
        answers = self.env['survey.user_input']

        for survey in surveys:
            existing_answers = self.env['survey.user_input'].search([
                ('survey_id', '=', survey.id),
                ('partner_id', 'in', partners.ids),
            ])
            partners_done, emails_done, _ = self._get_done_partners_emails(existing_answers)

            for new_partner in partners - partners_done:
                values = self._get_answers_values()
                values['project_id'] = self.project_id.id  # Set the project_id in the answers values
                answers |= survey._create_answer(partner=new_partner, check_attempts=False, **values)
        return answers


    def _get_done_partners_emails(self, existing_answers):
        answers = self.env['survey.user_input']
        partners_done = self.env['res.partner']
        emails_done = []
        if existing_answers:
            partners_done = existing_answers.mapped('partner_id')
            emails_done = existing_answers.mapped('email')

        return (partners_done, emails_done, answers)

    def _get_answers_values(self):
        return {
            'deadline': self.deadline,
        }

    def _set_subject(self, survey):
        """ Set the email subject based on the current survey. """
        self.subject = _("Participate in the survey: %(survey_name)s", survey_name=survey.display_name)



    def _send_mail(self, answer):
        """ Create mail specific for recipient containing notably its access token """
        email_from = self.template_id._render_field('email_from', answer.ids)[answer.id] if self.template_id.email_from else self.author_id.email_formatted
        if not email_from:
            raise UserError(_("Unable to post message, please configure the sender's email address."))
        subject = self._render_field('subject', answer.ids)[answer.id]
        body = self._render_field('body', answer.ids)[answer.id]
        
        # Post the message
        mail_values = {
            'attachment_ids': [(4, att.id) for att in self.attachment_ids],
            'auto_delete': True,
            'author_id': self.author_id.id,
            'body_html': body,
            'email_from': email_from,
            'model': None,
            'res_id': None,
            'subject': subject,
        }
        if answer.partner_id:
            mail_values['recipient_ids'] = [(4, answer.partner_id.id)]
        else:
            mail_values['email_to'] = answer.email

        # Optional support of default_email_layout_xmlid in context
        email_layout_xmlid = self.env.context.get('default_email_layout_xmlid', self.env.context.get('notif_layout'))
        if email_layout_xmlid:
            template_ctx = {
                'message': self.env['mail.message'].sudo().new(dict(body=mail_values['body_html'], record_name=self.survey_id.title)),
                'model_description': self.env['ir.model']._get('survey.survey').display_name,
                'company': self.env.company,
            }
            body = self.env['ir.qweb']._render(email_layout_xmlid, template_ctx, minimal_qcontext=True, raise_if_not_found=False)
            if body:
                mail_values['body_html'] = self.env['mail.render.mixin']._replace_local_links(body)
            else:
                _logger.warning('QWeb template %s not found or is empty when sending survey mails. Sending without layout', email_layout_xmlid)

        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.sudo().send()
        return mail

class ProjectAnalysis(models.Model):
    _inherit='project.project'
    
    def get_questionnaire(self):
        action = self.env.ref('survey.action_survey_user_input').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        return action


    def action_send_survey(self):
        """ Open a window to compose a survey invitation, pre-filled with the selected surveys and partners """
        # self.check_validity()

        template = self.env.ref('survey.mail_template_user_input_invite', raise_if_not_found=False)

        local_context = {

            'default_template_id': template.id if template else False,
            'default_email_layout_xmlid': 'mail.mail_notification_light',
            'default_send_email': True,
            'default_project_id':self.id,  # Add project_id to context
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _("Share Surveys"),
            'view_mode': 'form',
            'res_model': 'survey.invite',
            'target': 'new',
            'context': local_context,
        }

class MileDetail(models.Model):
    _name = 'mile.details'
    _description = 'Milestone Detail'

    name = fields.Char(string='Milestone Name', required=True)
    project_id = fields.Many2one('project.project', string='Project', ondelete='cascade')
    task_ids = fields.One2many('project.task', 'mile_id', string='Tasks')

class ProjectProject(models.Model):
    _inherit = 'project.project'

    mile_ids = fields.One2many('mile.details', 'project_id', string='Milestones')
 
class TasksAnalysis(models.Model):
    _inherit = 'project.task'

    mile_id = fields.Many2one('mile.details', string='Milestone')

class ActivityType(models.Model):
    _name = 'activity.type'
    _description = 'Activity Type'

    name = fields.Char(string='Name', required=True)


class UserInput(models.Model):
    _inherit = 'survey.user_input'

    issue_activities = fields.One2many('issue.activity', 'user_input_id', string='Issue Activities')
    review_status = fields.Selection([
        ('incomplete', 'Incomplete'),
        ('submitted', 'Submitted'),
        ('incorrect', 'Incorrect'),
        ('verified', 'Verified')
    ], string='Review Status', default='incomplete')
    submitted_by = fields.Selection([
        ('helper', 'Helper'),
        ('client', 'Client')
    ], string='Submitted By')

    survey_start_url = fields.Char('Survey Start URL', compute='_compute_survey_start_url')
    helper_ids = fields.Many2many('res.users', string='Helpers', compute='_compute_helper_ids', store=True)
    state = fields.Selection([
        ('new', 'Not started yet'),
        ('in_progress', 'In Progress'),
        ('done', 'Completed'),

        ], string='Status', default='new', readonly=True)

    def makeincorrect(self):
            return self.write({'review_status': 'incorrect'})

    def makeverified(self):
            return self.write({'review_status': 'verified'})

    @api.model
    def create(self, vals):
        if vals.get('state') in ['new', 'in_progress']:
            vals['review_status'] = 'incomplete'
        elif vals.get('state') in ['done']:
            vals['review_status'] = 'submitted'
        return super(UserInput, self).create(vals)


    def write(self, vals):
        if 'state' in vals and vals['state'] in ['new', 'in_progress']:
            vals['review_status'] = 'incomplete'
        elif vals.get('state') in ['done']:
            vals['review_status'] = 'submitted'
        return super(UserInput, self).write(vals)


 
    @api.depends('partner_id')
    def _compute_helper_ids(self):
        for record in self:
            if record.partner_id:
                participant = self.env['survey.participants'].search([('participant.partner_id', '=', record.partner_id.id)], limit=1)
                if participant:
                    record.helper_ids = [(6, 0, participant.helper_ids.ids)]
                else:
                    record.helper_ids = [(6, 0, [])]
            else:
                record.helper_ids = [(6, 0, [])]

    @api.depends('survey_id')
    def _compute_survey_start_url(self):
        for record in self:
            if record.survey_id:
                base_url = record.survey_id.get_base_url()
                # start_url = record.survey_id.get_start_url()
                specific_url = '%s?answer_token=%s' % (record.survey_id.get_start_url(), record.access_token)

                # identification_token = record.survey_id.access_token

                record.survey_start_url = werkzeug.urls.url_join(base_url, specific_url)
            else:
                record.survey_start_url = False


    @api.model
    def create(self, vals):
        # Check if survey_id and email or partner_id already exist
        existing_input = self.search([
            ('survey_id', '=', vals.get('survey_id')),
            ('partner_id', '=', vals.get('partner_id')),
        ])

        if existing_input:
            # Extract the IDs of the existing inputs
            existing_ids = tuple(existing_input.ids)

            if existing_ids:
                # Deleting existing user input directly from the db using cr.execute
                query = "DELETE FROM survey_user_input WHERE id IN %s"
                self._cr.execute(query, (existing_ids,))

        # Proceed with the creation of the new record
        return super(UserInput, self).create(vals)



        
class UserInputLine(models.Model):
    _inherit = 'survey.user_input.line'
    # _inherit = ['mail.thread', 'mail.activity.mixin']
 
    issue_activities = fields.One2many('issue.activity', 'user_input_line', string='Issue Activities', tracking=True)
    review_status = fields.Selection([
        ('incomplete', 'Incomplete'),
        ('submitted', 'Submitted'),
        ('incorrect', 'Incorrect'),
        ('verified', 'Verified')
    ], string='Review Status', default='incomplete',tracking=True)
    submitted_by = fields.Selection([
        ('helper', 'Helper'),
        ('client', 'Client')
    ], string='Submitted By')
    comment  = fields.Char(string="Comment")
    helper_ids = fields.Many2many('res.users', string='Helpers', compute='_compute_helper_ids', store=True)

    @api.depends('create_uid')
    def _compute_helper_ids(self):
        for record in self:
            if record.create_uid:
                participant = self.env['survey.participants'].search([('participant', '=', record.create_uid.id)], limit=1)
                if participant:
                    record.helper_ids = [(6, 0, participant.helper_ids.ids)]
                else:
                    record.helper_ids = [(6, 0, [])]
            else:
                record.helper_ids = [(6, 0, [])]



class IssueActivity(models.Model):
    _name = 'issue.activity'
    _description = 'Issue Activity'

    name = fields.Char(string='Description', required=True)
    user_input_id = fields.Many2one('survey.user_input', string='User Input')
    user_input_line = fields.Many2one('survey.user_input.line', string='User Input Line')
    

class SessionInherit(models.Model):
    _inherit = 'survey.survey'
    _description = 'Survey Session'

    participant_ids = fields.Many2many('res.partner', string='Participants')
    last_question_id = fields.Many2one('survey.question', string='Last Question')
    status = fields.Selection([
        ('started', 'Started'),
        ('paused', 'Paused'),
        ('waiting', 'Waiting'),
        ('terminated', 'Terminated')
    ], string='Status', default='started')
    survey_type = fields.Selection([
        ('survey', 'Quesionnaire'),
        ('live_session', 'Live session'),
        ('assessment', 'Assessment'),
        ('custom', 'Custom'),
    ],
        string='Survey Type', required=True, default='custom')

class Participant(models.Model):
    _name = 'survey.participants'
    participant = fields.Many2one('res.users', string="Participant")
    helper_ids = fields.Many2many('res.users', string='Helpers')

    @api.onchange('helper_ids')
    def _onchange_participant(self):
        for record in self:
            if record.participant:
                survey_user_inputs = self.env['survey.user_input'].sudo().search([('partner_id', '=', record.participant.partner_id.id)])
                for input_record in survey_user_inputs:
                    _logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
                    _logger.info(input_record.partner_id.name)
                    input_record.helper_ids = [(6, 0, record.helper_ids.ids)]

                survey_user_inputs_line = self.env['survey.user_input.line'].sudo().search([('create_uid', '=', record.participant.id)])
                for input_record in survey_user_inputs_line:
                    _logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
                    # _logger.info(input_record.crea.name)
                    input_record.helper_ids = [(6, 0, record.helper_ids.ids)]
