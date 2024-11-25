from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers import portal
from odoo.addons.portal.controllers.portal import CustomerPortal, pager
from collections import OrderedDict

class CustomerPortal(portal.CustomerPortal):
    """This class inherits controller portal"""
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        
        if 'survey_count' in counters:
            # Update the count of StockQuantPallet records
            survey_count = request.env['survey.user_input'].search_count([('partner_id.id', '=', request.env.user.partner_id.id)])
            if survey_count>0:
                values['survey_count'] = survey_count
            else:
                values['survey_count'] = 1
        return values

    @http.route(['/my_survey', '/my_survey/page/<int:page>'], type='http', auth="user", website=True)
    def my_survey_portal(self, filterby=None, sortby='date',groupby="none"):
        """To add filter and sorting for records in the website portal"""
        searchbar_sortings = {
            'date': {'label': _('Created date'), 'order': 'create_date desc'},
        }

        if sortby not in searchbar_sortings:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
        }
        if not filterby:
            filterby = 'all'
        domain = searchbar_filters[filterby]['domain']
        # Combine domain and sort order in the search query
        my_surveys = request.env['survey.user_input'].sudo().search(
            [('partner_id.id', '=', request.env.user.partner_id.id)],   # Combining partner and domain filters
            order=order
        )
        total_pallets = len(my_surveys)
        page_detail = pager(
            url='/my_survey', total=total_pallets, 
            url_args={'filterby': filterby, 'sortby': sortby,'groupby':groupby}
        )
        return request.render("questionnaires.portal_survey_user_input", {
            'surveys': my_surveys,
            'page_name': 'my_survey',
            'pager': page_detail,
            'default_url': '/my_survey',
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
