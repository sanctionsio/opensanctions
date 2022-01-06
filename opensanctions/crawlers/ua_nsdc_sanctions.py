import json
from pantomime.types import JSON
from followthemoney.types import registry

from opensanctions.core import Context
from opensanctions import helpers as h
from opensanctions.util import multi_split

PHYSICAL_URL = "https://sanctions-t.rnbo.gov.ua/api/fizosoba/"
LEGAL_URL = "https://sanctions-t.rnbo.gov.ua/api/jurosoba/"


async def json_resource(context: Context, url, name):
    path = await context.fetch_resource(f"{name}.json", url)
    await context.export_resource(path, JSON, title=context.SOURCE_TITLE)
    with open(path, "r") as fh:
        return json.load(fh)


async def handle_address(context: Context, entity, text):
    if text is None:
        return
    country = text
    if "," in country:
        country, _ = country.split(",", 1)
    code = registry.country.clean(country, fuzzy=True)
    if code is not None:
        entity.add("country", code)
    address = h.make_address(context, full=text, country_code=code)
    await h.apply_address(context, entity, address)


async def handle_sanction(context, entity, row):
    sanction = h.make_sanction(context, entity)
    sanction.add("status", row.pop("action", None))
    sanction.add("summary", row.pop("restriction_period", None))
    sanction.add("program", row.pop("restriction_type", None))
    sanction.add("startDate", row.pop("ukaz_date", None))
    sanction.add("endDate", row.pop("restriction_end_date", None))
    await context.emit(sanction)


async def crawl_physical(context: Context) -> None:
    data = await json_resource(context, PHYSICAL_URL, "physical")
    for row in data:
        entity = context.make("Person")
        entity.id = context.make_slug(row.pop("ukaz_id"), row.pop("index"))
        entity.add("name", row.pop("name_ukr", None))
        entity.add("name", row.pop("name_original", None))
        for alias in multi_split(row.pop("name_alternative", None), [";", "/"]):
            entity.add("alias", alias)
        entity.add("notes", row.pop("additional", None))
        for country in multi_split(row.pop("citizenship", None), [", "]):
            entity.add("nationality", country)
        entity.add("birthDate", row.pop("birthdate", None))
        entity.add("birthPlace", row.pop("birthplace", None))
        entity.add("position", row.pop("occupation", None))
        await handle_address(context, entity, row.pop("livingplace", None))
        await handle_sanction(context, entity, row)

        await context.emit(entity, target=True)
        # context.pprint(row)


async def crawl_legal(context: Context) -> None:
    data = await json_resource(context, LEGAL_URL, "legal")
    for row in data:
        entity = context.make("Organization")
        entity.id = context.make_slug(row.pop("ukaz_id"), row.pop("index"))
        entity.add("name", row.pop("name_ukr", None))
        entity.add("name", row.pop("name_original", None))
        for alias in multi_split(row.pop("name_alternative", None), [";", "/"]):
            entity.add("alias", alias)
        entity.add("notes", row.pop("additional", None))
        ipn = row.pop("ipn", "") or ""
        entity.add("taxNumber", ipn.replace("ІПН", ""))
        odrn = row.pop("odrn_edrpou", "") or ""
        entity.add("registrationNumber", odrn.replace("ОДРН", ""))

        await handle_address(context, entity, row.pop("place", None))
        await handle_address(context, entity, row.pop("place_alternative", None))
        await handle_sanction(context, entity, row)
        # context.pprint(row)
        await context.emit(entity, target=True, unique=True)


async def crawl(context: Context) -> None:
    await crawl_physical(context)
    await crawl_legal(context)
