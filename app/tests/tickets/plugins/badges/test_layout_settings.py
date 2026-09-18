import datetime

from django.test import override_settings
from django_scopes import scopes_disabled

from eventyay.base.models import Event, Organizer, Team, User
from tests.tickets.base import SoupTest


@override_settings(SITE_URL='https://testserver')
class BadgeLayoutSettingsViewTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.organizer = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.organizer,
            name='30C3',
            slug='30c3',
            plugins='eventyay.plugins.badges',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.UTC),
        )
        team = Team.objects.create(
            organizer=self.organizer,
            can_change_event_settings=True,
            all_events=True,
        )
        team.members.add(self.user)
        with scopes_disabled():
            self.layout = self.event.badge_layouts.create(name='Layout 1', default=True)
        self.client.login(email='dummy@dummy.dummy', password='dummy')
        self.url = f'/control/event/{self.organizer.slug}/{self.event.slug}/badges/{self.layout.pk}/settings'

    def test_field_settings_persist_when_customization_is_off(self):
        response = self.client.post(
            self.url,
            {
                'ask_user_fields': ['attendee_job_title', 'attendee_company'],
                'required_badge_fields': ['attendee_job_title', 'attendee_company'],
            },
        )
        assert response.status_code == 302

        self.layout.refresh_from_db()
        assert not self.layout.allow_customization
        assert set(self.layout.ask_user_fields_data) == {'attendee_job_title', 'attendee_company'}
        assert set(self.layout.required_badge_fields_data) == {'attendee_job_title', 'attendee_company'}

    def test_disabling_customization_keeps_field_settings(self):
        response = self.client.post(
            self.url,
            {
                'allow_customization': 'on',
                'ask_user_fields': ['attendee_company'],
                'required_badge_fields': ['attendee_company'],
            },
        )
        assert response.status_code == 302

        self.layout.refresh_from_db()
        assert self.layout.allow_customization

        response = self.client.post(
            self.url,
            {
                'ask_user_fields': ['attendee_company'],
                'required_badge_fields': ['attendee_company'],
            },
        )
        assert response.status_code == 302

        self.layout.refresh_from_db()
        assert not self.layout.allow_customization
        assert self.layout.ask_user_fields_data == ['attendee_company']
        assert self.layout.required_badge_fields_data == ['attendee_company']
