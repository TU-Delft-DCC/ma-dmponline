import json
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail

from stats.helpers import get_md5
from stats.mappings import Mappings, AvgRegistry, ESBConnection, SharePointConn
from stats.models import (
    DMP,
    DataUser,
    DataType,
    ShareType,
    StorageLocation,
    FacultyDepartment,
)

logger = logging.getLogger("main")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-b", "--begin", type=int)
        parser.add_argument("-e", "--end", type=int)

    def handle(self, *args, **options):
        # begin and end ints are for pages
        # requested from DMP online
        begin = options["begin"] if options["begin"] else 267
        end = options["end"] if options["end"] else 269
        logger.info(f"Fetching from page {begin} to {end}")
        dj_avg_del = (
            sp_avg_del
        ) = (
            stats_avg_del
        ) = (
            dj_avg_ins
        ) = (
            dj_avg_upd
        ) = (
            sp_avg_ins
        ) = (
            sp_avg_upd
        ) = (
            dj_avg_fail
        ) = (
            sp_avg_fail
        ) = stats_ins = total_dmps = mappable_dmps = td_ins = td_ins_ok = 0
        # get all existing AVG register lines
        logger.info("Getting all AVG register lines...")
        avg_register = AvgRegistry().get_all().json()
        logger.info(f"Found {len(avg_register)} AVG lines")

        # get all existing DMP ids
        logger.info("Getting all DMP ids from DMPonline...")
        all_plan_ids = Mappings().get_all_plan_ids()
        logger.info(f"Found {len(all_plan_ids)} plan ids")

        # check if AVG line is still in DMPonline,
        # else remove AVG line and remove from stats
        for avg_line in avg_register:
            if int(avg_line["sourcekey"]) not in all_plan_ids:
                logger.info(
                    f"Deleting AVG line {avg_line['avgregisterline']['id']} (DMP id {avg_line['sourcekey']})"
                    f" from registry and statistics..."
                )
                e, a = AvgRegistry().remove_record(
                    avg_line["sourcekey"], avg_line["avgregisterline"]["id"]
                )
                dj_avg_del += 1
                if e.status_code == a.status_code == 204:
                    logger.info(
                        f"Succesfully deleted DMP with id {avg_line['sourcekey']}"
                    )
                else:
                    logger.info(f"{e.status_code}, {a.status_code}, {e.text}, {a.text}")
                n = DMP.objects.filter(dmp_id=avg_line["sourcekey"]).delete()
                stats_avg_del += 1
                logger.info(f"Deleted {n} items from stats.")

                # TODO: delete AVG line from SharePoint, as of now,
                #  we don't have a reference to corresponding SharePoint ID

        for i in range(begin, end):  # 69, 269
            logger.info(f"Page {i}")

            # get all 10 DMPs from this page
            page = Mappings().get_page(i)

            for item in page:
                total_dmps += 1
                plan = Mappings()
                is_updated = is_inserted = False

                plan.set_plan_by_dict(item)  # sets plan.plan
                if plan.is_mappable() and not (
                    plan.is_test_plan() if not settings.PARSE_TEST_PLANS else False
                ):
                    mappable_dmps += 1
                    # uses all the functions in mappings to decide
                    # on mappings
                    avg_mappings = plan.get_avg_mappings()
                    logger.info(f"Found plan {str(plan.get_id())}")
                    avg_line = plan_in_avg_register(plan, avg_register)

                    logger.info(
                        f"Inserting {plan.get_id()} into SharePoint AVG list..."
                    )
                    sp_inserted = SharePointConn().insert_avg_line(
                        plan.get_sp_avg_mappings()
                    )
                    if sp_inserted:
                        sp_avg_ins += 1
                        logger.info("Inserting into SharePoint: OK")
                    # TODO: We need a reference to the corresponding SharePoint AVG line
                    #  otherwise we would just keep adding already existing lines
                    else:
                        sp_avg_fail += 1

                    if avg_line:
                        # plan is already in AVG registry
                        # update it anyway (AVG reg. has no last updated)
                        is_updated = update_avg_register(
                            avg_mappings, avg_line["avgregisterline"]["id"]
                        )
                        if is_updated:
                            dj_avg_upd += 1
                        else:
                            dj_avg_fail += 1
                        # TODO: We need a reference to the corresponding SharePoint AVG line
                        #  otherwise we would just keep adding already existing lines
                    else:  # plan should be inserted into AVG registry
                        is_inserted = insert_avg_register(avg_mappings)
                        if is_updated:
                            dj_avg_ins += 1
                        else:
                            dj_avg_fail += 1

                    # esb = ESBConnection()
                    # logger.info("Creating TOPdesk ticket for storage")
                    # td_ins += 1
                    # r = esb.create_topdesk_ticket(plan.get_esb_mappings())
                    # logger.info(r.status_code)
                    # if r.status_code == 200:
                    #    td_ins_ok += 1
                    # TODO: TOPdesk tickets should only be created when corresponding checkbox
                    #  is ticked and the plan is new. This is something to decide on because most
                    #  plans have a difference between date_created and date_last_updated

                    # now get faculty/dep. info from ESB and insert into (anonymous stats DB)
                    if is_inserted or is_updated:
                        insert_statistics(plan)
                        stats_ins += 1
                    else:
                        # report_raw_insert(avg_mappings)  # this is dirty, because sometimes it works
                        # and then, no external ref is added.
                        send_mail(
                            "Updating or inserting into AVG registry failed",
                            "Updating or inserting into AVG registry failed for DMP id"
                            + str(plan.get_id()),
                            settings.DEFAULT_FROM_EMAIL,
                            [settings.DEFAULT_RECIPIENT],
                            fail_silently=False,
                        )

                    if plan.key_error_occurred is False:
                        logger.info("No key errors occurred " + str(plan.get_id()))

                    logger.info("Done processing " + str(plan.get_id()))
                    """dj_avg_del = sp_avg_del = stats_avg_del = dj_avg_ins = dj_avg_upd = sp_avg_ins = sp_avg_upd = \
                        dj_avg_fail = sp_avg_fail = stats_ins = total_dmps = mappable_dmps = td_ins = td_ins_ok = 0"""
        logger.info(f"Total DMPs found: {total_dmps}")
        logger.info(f"Total mappable DMPs: {mappable_dmps}")
        logger.info(f"Django AVG lines inserted: {dj_avg_ins}")
        logger.info(f"Django AVG lines updated: {dj_avg_upd}")
        logger.info(f"Django AVG lines failed (ins/upd): {dj_avg_fail}")
        logger.info(f"SharePoint AVG lines inserted: {sp_avg_ins}")
        logger.info(f"SharePoint AVG lines failed: {sp_avg_fail}")
        logger.info(f"Statistics lines inserted {stats_ins}")
        logger.info(f"Django AVG lines deleted: {dj_avg_del}")
        logger.info(f"Statistics lines deleted: {stats_avg_del}")


def plan_in_avg_register(plan, avg_register):
    for avg_line in avg_register:
        try:
            avg_source_key = avg_line["sourcekey"]
        except ValueError:
            avg_source_key = None
        except KeyError:
            avg_source_key = None
        if avg_source_key:
            avg_source_key = int(avg_source_key)
        if avg_source_key == plan.get_id():
            logger.info(f"Found avg_line {str(avg_line['avgregisterline']['id'])}")
            return avg_line


def update_avg_register(avg_mappings, avg_id):
    result = AvgRegistry().update_record(avg_mappings, avg_id=avg_id)
    if result.status_code == 200:  # updated
        logger.info("AVG registry updated in update_avg_register()")
        return True
    else:
        logger.error("AVG registry update FAILED")
        logger.error(result.text)
        return False


def insert_avg_register(avg_mappings):
    result = AvgRegistry().insert_record(avg_mappings)
    if result.status_code == 201:  # created
        logger.info("Inserted into AVG registry")
        return True
    elif result.status_code == 200:  # updated
        logger.warning(
            "Inserted into AVG registry got 200 (OK) response: THIS IS WEIRD!!!"
        )
        logger.warning(result.status_code)
        return True
    elif result.status_code == 400:  # something is wrong
        logger.error("AVG registry insert FAILED")
        logger.error(result.status_code)
        with open(f"failed_dmp-{avg_mappings['sourcekey']}.json", "w") as out:
            out.write(json.dumps(avg_mappings))
        return False
    else:
        logger.error("AVG registry insert FAILED")
        logger.error(result.status_code)
        with open(f"failed_dmp-{avg_mappings['sourcekey']}.json", "w") as out:
            out.write(json.dumps(avg_mappings))
        return False


def insert_statistics(plan):
    esb = ESBConnection()
    dmp = DMP()
    dmp.dmp_id = plan.get_id()
    try:
        logger.info(dmp.dmp_id)
        dmp = DMP.objects.get(dmp_id=dmp.dmp_id)
        logger.info("Exists in stats")
    except DMP.DoesNotExist:
        logger.info("Does not exist in stats, adding to stats...")
        dmp.type = plan.get_template_id()
        dmp.template_name = plan.get_template_name()
        dmp.personal_data = plan.has_personal_data()
        dmp.human_participants = plan.has_human_participants()

        # many variables are often not filled out
        try:
            data_amount = int(plan.get_storage_amount().split(" ")[-2])
            if data_amount == 5:
                data_amount *= 1000  # quick and dirty
            dmp.data_amount = data_amount
            # TODO: handle > 5 TB option properly
        except AttributeError:
            pass
        dmp.confidential_data = plan.has_confidential_data()
        try:
            data_amount_public = int(plan.get_storage_amount_public().split(" ")[-2])
            if data_amount_public == 1:
                data_amount_public *= 1000  # quick & dirty
            dmp.data_amount_public = data_amount_public
            # TODO: handle > 1 TB option properly
        except AttributeError:
            pass
        dmp.save()

    for data_type in plan.get_data_types():
        dt, created = DataType.objects.get_or_create(name=data_type)
        dmp.data_types_public.add(dt)

    for share_type in plan.get_share_types():
        st, created = ShareType.objects.get_or_create(name=share_type)
        dmp.share_types.add(st)

    for storage_location in plan.get_storage_locations_stats():
        sl, created = StorageLocation.objects.get_or_create(name=storage_location)
        dmp.storage_locations.add(sl)

    for user in plan.plan["users"]:
        data_user = DataUser()

        # this comes from ESB
        faculty_department = "-".join(esb.get_department(user["email"]))

        if faculty_department:
            fd, created = FacultyDepartment.objects.get_or_create(
                name=faculty_department
            )
            data_user.faculty_department = fd

        data_user.dmp = dmp

        data_user.email_hash = get_md5(user["email"])
        data_user.save()
    logger.info("Successfully added to / updated in stats.")
