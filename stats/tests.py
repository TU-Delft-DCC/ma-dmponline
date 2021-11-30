import json

import requests
from django.conf import settings

from stats.mappings import Mappings, SharePointConn, ESBConnection, AvgRegistry
import responses


def test_plan_mappings(request):
    # instantiate Mappings but do not make
    # contact with any 'real' servers (do_init=False)
    mapping = Mappings(token=None, base_url=None, do_init=False)

    with open("test_files/out.json") as f:
        mapping.set_plan_by_dict(json.load(f))
    assert mapping.plan
    assert mapping.get_id() == 83643
    assert mapping.get_template_id() == 975303870

    avg_line = mapping.get_avg_mappings()
    request.config.cache.set("django_avg_line", avg_line)
    request.config.cache.set("sp_avg_line", mapping.get_sp_avg_mappings())
    request.config.cache.set("esb_mappings", mapping.get_esb_mappings())

    assert avg_line["avgregisterline"]["eigenaar"] == "-"
    assert mapping.get_legal_ground() == "-"
    assert mapping.get_storage_amount() == "250 TB"
    assert avg_line["avgregisterline"]["verwerking"].startswith("Develop")

    esb = mapping.get_esb_mappings()
    assert esb["driveName"] == "Project Storage at TU Delft"
    assert not mapping.has_confidential_data()
    assert mapping.get_data_types() == [
        "Not all data can be publicly shared - please explain below which data and why"
        " cannot be publicly shared"
    ]
    assert mapping.get_share_types() == [
        "My data will be shared in a different way - please explain below"
    ]
    assert mapping.get_storage_amount_public() is None
    assert mapping.has_study_or_employ_info() is None
    assert mapping.has_special_categories() is None
    assert type(mapping.get_storage_locations_stats()) == set
    assert mapping.get_last_updated() == "2021-09-16T12:37:56"
    assert not mapping.is_test_plan()
    assert mapping.is_mappable()
    assert not mapping.has_personal_data()
    assert mapping.has_human_participants()


@responses.activate
def test_get_start_date():
    responses.add(
        responses.POST,
        settings.DMPONLINE_AUTH_URL,
        json={"access_token": "foo"},
        status=200,
    )

    with open("test_files/out2.json") as f:
        responses.add(
            responses.GET,
            f"{settings.DMPONLINE_API_V1_URL}plans/{83643}",
            json=json.load(f),
            status=200,
        )

    dates = Mappings().get_start_end_date(83643)

    assert dates == ("2021-07-12T00:00:00Z", "2021-12-17T00:00:00Z")


@responses.activate
def test_get_all_plan_ids():
    responses.add(
        responses.POST,
        settings.DMPONLINE_AUTH_URL,
        json={"access_token": "foo"},
        status=200,
    )

    with open("test_files/out3.json") as f:
        responses.add(
            responses.GET,
            settings.DMPONLINE_API_V0_URL + "statistics/plans",
            json=json.load(f),
            status=200,
        )

    plans = Mappings().get_all_plan_ids()
    assert 84852 in plans

    responses.remove(responses.GET, settings.DMPONLINE_API_V0_URL + "statistics/plans")
    responses.add(
        responses.GET, settings.DMPONLINE_API_V0_URL + "statistics/plans", status=400
    )

    plans = Mappings().get_all_plan_ids()
    assert plans is False


@responses.activate
def test_get_page(request):
    responses.add(
        responses.POST,
        settings.DMPONLINE_AUTH_URL,
        json={"access_token": "foo"},
        status=200,
    )
    with open("test_files/out4.json") as f:
        responses.add(
            responses.GET,
            f"{settings.DMPONLINE_API_V0_URL}plans?page=200",
            json=json.load(f),
            status=200,
        )
    request.config.cache.set("plans", Mappings().get_page(200))
    assert request.config.cache.get("plans", None)[0]["id"] == 76258


@responses.activate
def test_set_plan(request):
    responses.add(
        responses.POST,
        settings.DMPONLINE_AUTH_URL,
        json={"access_token": "foo"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{settings.DMPONLINE_API_V0_URL}plans?plan=76258",
        json=request.config.cache.get("plans", None),
        status=200,
    )  # reuse from previous test
    m = Mappings()
    m.set_plan(76258)
    request.config.cache.set("plan", m.plan)
    assert m.plan["id"] == 76258


def test_set_plan_by_dict(request):
    n = Mappings()
    n.set_plan_by_dict(request.config.cache.get("plan", None))
    assert n.plan["id"] == 76258


@responses.activate
def test_sp_form_digest_value():
    sp_conn = SharePointConn()
    responses.add(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/contextinfo",
        json={"d": {"GetContextWebInformation": {"FormDigestValue": "foo"}}},
        status=200,
    )
    assert sp_conn.get_form_digest_value() == "foo"


@responses.activate
def test_sp_avg_line(request):
    responses.add(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/contextinfo",
        json={"d": {"GetContextWebInformation": {"FormDigestValue": "foo"}}},
        status=200,
    )
    sp_conn = SharePointConn()
    responses.add(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items",
        status=201,
    )

    sp_avg_line = request.config.cache.get("sp_avg_line", None)
    assert sp_conn.insert_avg_line(sp_avg_line)

    responses.remove(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items",
    )
    responses.add(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items",
        status=200,
    )
    assert not sp_conn.insert_avg_line(sp_avg_line)

    responses.remove(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items",
    )
    responses.add(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items(1)",
        status=200,
    )

    assert sp_conn.update_avg_line(sp_avg_line, 1)

    responses.remove(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items(1)",
    )
    responses.add(
        responses.POST,
        settings.SHAREPOINT_URL + "sites/dmponline2avg/avg/_api/"
        "web/lists/GetByTitle(%27AVG%27)/items(1)",
        status=400,
    )

    assert not sp_conn.update_avg_line(sp_avg_line, 1)


@responses.activate
def test_get_department():
    responses.add(
        responses.GET,
        settings.ESB_URL + "faculty/get?emailAdres=test@adres.com",
        json={
            "organisatieEenheid": {"afkortingNLVolledig": "TNW-BT-BTS"},
            "accountLifecycleFase": "grace",
        },
        status=200,
    )
    e = ESBConnection()

    assert e.get_department("test@adres.com") == ("TNW", "BT")
    responses.remove(
        responses.GET, settings.ESB_URL + "faculty/get?emailAdres=test@adres.com"
    )

    responses.add(
        responses.GET,
        settings.ESB_URL + "faculty/get?emailAdres=test@adres.com",
        json={"faculteitId": "bla", "accountLifecycleFase": "grace"},
        status=200,
    )
    e = ESBConnection()
    assert e.get_department("test@adres.com") == ("bla", "")


@responses.activate
def test_create_topdesk_ticket(request):
    responses.add(
        responses.POST, settings.ESB_URL + "storage/request/create", status=200
    )

    assert (
        ESBConnection(token="")
        .create_topdesk_ticket(request.config.cache.get("esb_mappings", None))
        .status_code
        == 200
    )


@responses.activate
def test_django_avg_line(request):
    responses.add(
        responses.POST,
        settings.AVG_REGISTRY_URL + "avgregisterline/external/",
        status=200,
    )
    responses.add(
        responses.POST, settings.AVG_REGISTRY_URL + "avgregisterline/", status=200
    )
    responses.add(responses.POST, settings.AVG_REGISTRY_URL + "externals/", status=200)
    responses.add(responses.GET, settings.AVG_REGISTRY_URL + "externals/", status=200)
    responses.add(
        responses.DELETE, settings.AVG_REGISTRY_URL + "avgregisterline/1/", status=200
    )
    responses.add(
        responses.PUT, settings.AVG_REGISTRY_URL + "avgregisterline/1/", status=200
    )
    responses.add(
        responses.DELETE, settings.AVG_REGISTRY_URL + "externals/1/", status=200
    )
    avg_line = request.config.cache.get("django_avg_line", None)

    assert AvgRegistry().insert_record(avg_line).status_code == 200
    assert AvgRegistry().update_record(avg_line, 1).status_code == 200
    assert AvgRegistry().get_all().status_code == 200
    e, a = AvgRegistry().remove_record(1, 1)
    assert e.status_code, a.status_code == (200, 200)
