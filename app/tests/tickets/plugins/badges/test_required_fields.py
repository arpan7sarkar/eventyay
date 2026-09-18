import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django_scopes import scopes_disabled

from eventyay.base.models import Event, Order, OrderPosition, Organizer, Product
from eventyay.plugins.badges.forms import BadgeOptionsField
from eventyay.plugins.badges.models import BadgeProduct
from eventyay.plugins.badges.signals import BADGE_HIDDEN_FIELDS_KEY, badge_question_form_fields
from eventyay.plugins.badges.utils import (
    get_badge_hidden_fields,
    save_badge_customization,
    validate_badge_hidden_fields,
)
from eventyay.plugins.badges.exporters import BadgeRenderer


@pytest.fixture
def badge_customization_env():
    with scopes_disabled():
        organizer = Organizer.objects.create(name='CCC', slug='ccc')
        event = Event.objects.create(
            organizer=organizer,
            name='30C3',
            slug='30c3',
            plugins='eventyay.plugins.badges',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        product = Product.objects.create(
            event=event,
            name='Standard',
            default_price=0,
            admission=True,
            position=1,
        )
        order = Order.objects.create(
            event=event,
            email='dummy@dummy.test',
            status=Order.STATUS_PAID,
            datetime=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            expires=datetime.datetime(2014, 1, 26, tzinfo=datetime.timezone.utc),
            total=0,
        )
        position = OrderPosition.objects.create(
            order=order,
            product=product,
            price=Decimal('0.00'),
            attendee_name_parts={'full_name': 'Ada Lovelace', '_scheme': 'full'},
            secret='secret-badge-1',
        )
        layout = event.badge_layouts.create(
            name='Layout 1',
            default=True,
            allow_customization=True,
            allow_badge_editing=True,
        )
        layout.ask_user_fields_data = ['attendee_name', 'attendee_company']
        layout.required_badge_fields_data = ['attendee_name']
        layout.save(update_fields=['ask_user_fields', 'required_badge_fields'])

        return {
            'organizer': organizer,
            'event': event,
            'product': product,
            'order': order,
            'position': position,
            'layout': layout,
        }


@pytest.mark.django_db
def test_validate_badge_hidden_fields_rejects_required(badge_customization_env):
    event = badge_customization_env['event']
    position = badge_customization_env['position']

    # Hiding attendee_company is allowed (not required)
    result = validate_badge_hidden_fields(event, position, ['attendee_company'])
    assert result == ['attendee_company']

    # Hiding attendee_name is NOT allowed (required)
    with pytest.raises(ValidationError) as exc:
        validate_badge_hidden_fields(event, position, ['attendee_name'])
    assert 'required and cannot be hidden' in str(exc.value)

    # Hiding both fails
    with pytest.raises(ValidationError) as exc:
        validate_badge_hidden_fields(event, position, ['attendee_name', 'attendee_company'])
    assert 'required and cannot be hidden' in str(exc.value)


@pytest.mark.django_db
def test_badge_options_field_clean_auto_adds_required(badge_customization_env):
    # Setup field with required_keys
    field = BadgeOptionsField(
        choices=[('attendee_name', 'Name'), ('attendee_company', 'Company')],
        required_keys=['attendee_name'],
    )

    # User submits only 'attendee_name' selected (attendee_company is hidden)
    result = field.clean(['attendee_name'])
    assert result == ['attendee_company']

    # User submits empty selection (both hidden in POST because required is disabled) - should auto-add name
    result = field.clean([])
    assert result == ['attendee_company']

    # User submits only 'attendee_company' selected (attendee_name is hidden in POST) - should auto-add name
    result = field.clean(['attendee_company'])
    assert result == []


@pytest.mark.django_db
def test_badge_renderer_ignores_hidden_if_required(badge_customization_env):
    position = badge_customization_env['position']
    event = badge_customization_env['event']
    layout = badge_customization_env['layout']

    # Setup the backend layout where attendee_name and attendee_company are hidden in DB
    save_badge_customization(position, hidden_fields=['attendee_name', 'attendee_company'])

    # Setup the renderer
    renderer = BadgeRenderer(
        event,
        layout.layout_data,
        None,
        ask_user_fields=layout.ask_user_fields_data,
        required_fields=layout.required_badge_fields_data,
    )

    # Get effective hidden fields
    hidden = renderer._get_layout_hidden_fields(position)

    # The required field (attendee_name) should be stripped from the hidden list,
    # meaning it WILL be rendered.
    assert 'attendee_name' not in hidden
    assert 'attendee_company' in hidden


@pytest.fixture
def badge_bundle_env():
    with scopes_disabled():
        organizer = Organizer.objects.create(name='CCC', slug='ccc')
        event = Event.objects.create(
            organizer=organizer,
            name='30C3',
            slug='30c3',
            plugins='eventyay.plugins.badges',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.UTC),
        )
        root_product = Product.objects.create(event=event, name='Ticket', default_price=0, admission=True, position=1)
        addon_product = Product.objects.create(event=event, name='Workshop', default_price=0, position=2)

        root_layout = event.badge_layouts.create(name='Root layout', allow_customization=False)
        root_layout.required_badge_fields_data = ['attendee_job_title']
        root_layout.save(update_fields=['required_badge_fields'])
        addon_layout = event.badge_layouts.create(name='Add-on layout', allow_customization=True)
        addon_layout.ask_user_fields_data = ['attendee_job_title']
        addon_layout.save(update_fields=['ask_user_fields'])

        BadgeProduct.objects.create(product=root_product, layout=root_layout)
        BadgeProduct.objects.create(product=addon_product, layout=addon_layout)

        order = Order.objects.create(
            event=event,
            email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=datetime.datetime(2013, 12, 26, tzinfo=datetime.UTC),
            expires=datetime.datetime(2014, 1, 26, tzinfo=datetime.UTC),
            total=0,
        )
        root_position = OrderPosition.objects.create(
            order=order,
            product=root_product,
            price=Decimal('0.00'),
            positionid=1,
            secret='secret-bundle-root',
        )
        OrderPosition.objects.create(
            order=order,
            product=addon_product,
            price=Decimal('0.00'),
            positionid=2,
            addon_to=root_position,
            secret='secret-bundle-addon',
        )

        return {
            'event': event,
            'root_position': root_position,
        }


@pytest.mark.django_db
def test_bundle_ignores_required_fields_of_uncustomizable_root_layout(badge_bundle_env):
    event = badge_bundle_env['event']
    root_position = badge_bundle_env['root_position']

    with scopes_disabled():
        fields = badge_question_form_fields(sender=event, position=root_position)

    # The add-on layout allows customization, so the bundle still offers its field.
    field = fields[BADGE_HIDDEN_FIELDS_KEY]
    assert [value for value, _label in field.choices] == ['attendee_job_title']

    # The root layout does not allow customization, so it must not force any field.
    assert field.required_keys == set()
    assert field.clean([]) == ['attendee_job_title']
