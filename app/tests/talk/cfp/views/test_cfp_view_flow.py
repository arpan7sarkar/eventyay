import datetime as dt

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope


def _cfp_url(event):
    return reverse('cfp:event.start', kwargs={'event': event.slug, 'organizer': event.organizer.slug})


def _publish_talks(event):
    with scope(event=event):
        event.talks_published = True
        event.save(update_fields=['talks_published'])


@pytest.mark.django_db
def test_cfp_landing_page_has_page_title_when_open(client, event):
    _publish_talks(event)
    response = client.get(_cfp_url(event))
    assert response.status_code == 200
    doc = BeautifulSoup(response.rendered_content, 'lxml')
    headings = doc.select('main h1.page-title')
    assert len(headings) == 1
    assert headings[0].get_text(strip=True) == 'Call for Speakers'


@pytest.mark.django_db
def test_cfp_landing_page_has_page_title_when_closed(client, event):
    _publish_talks(event)
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
    response = client.get(_cfp_url(event))
    assert response.status_code == 200
    doc = BeautifulSoup(response.rendered_content, 'lxml')
    headings = doc.select('main h1.page-title')
    assert len(headings) == 1
    assert headings[0].get_text(strip=True) == 'Call for Speakers (Closed)'


@pytest.mark.django_db
def test_cfp_headline_renders_as_lede_paragraph_not_heading(client, event):
    _publish_talks(event)
    with scope(event=event):
        event.cfp.headline = 'Come talk to us'
        event.cfp.save()
    response = client.get(_cfp_url(event))
    assert response.status_code == 200
    doc = BeautifulSoup(response.rendered_content, 'lxml')
    ledes = doc.select('main p.page-lede')
    assert len(ledes) == 1
    assert ledes[0].get_text(strip=True) == 'Come talk to us'
    headings = doc.select('main h1, main h2, main h3, main h4')
    assert not any('Come talk to us' in heading.get_text() for heading in headings)


@pytest.mark.django_db
def test_empty_cfp_headline_renders_no_lede_and_no_empty_heading(client, event):
    _publish_talks(event)
    response = client.get(_cfp_url(event))
    assert response.status_code == 200
    doc = BeautifulSoup(response.rendered_content, 'lxml')
    assert len(doc.select('main p.page-lede')) == 0
    assert len(doc.select('main h2.content-header')) == 0
