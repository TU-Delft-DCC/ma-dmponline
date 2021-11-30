import logging
import os
import json
import requests
import inspect
from datetime import datetime
from requests_ntlm import HttpNtlmAuth
from django.conf import settings
from stats.helpers import html_table_to_list, clean_html, remove_special_chars_from_list

requests.packages.urllib3.disable_warnings()

logger = logging.getLogger("mappings")

MAPPABLE_IDS = (
    # 1753695087,  # Data Management Plan NWO (September 2020)
    975303870,  # TU Delft Data Management Plan template (2021)
    # 1165855271,  # TU Delft Data Management Questions
    # 1506827492,  # NWO Data Management Plan (January 2020)
    # 1461074155,  # Data management ZonMw-template 2019
)


class SharePointConn:
    def __init__(
        self,
        base_url=settings.SHAREPOINT_URL,
        username=settings.SHAREPOINT_USERNAME,
        password=settings.SHAREPOINT_PASSWORD,
    ):
        self.base_url = base_url
        self.headers = {
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
        }
        self.auth = HttpNtlmAuth(username, password)

    def get_form_digest_value(self):
        response = requests.post(
            url=self.base_url + "sites/dmponline2avg/avg/_api/contextinfo",
            headers=self.headers,
            auth=self.auth,  # authenticating also yields a token, but
            # it does not seem to work in subsequent
            # requests, so we'll keep using auth.
        )
        return response.json()["d"]["GetContextWebInformation"]["FormDigestValue"]

    def insert_avg_line(self, sp_avg_line):
        headers = {
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
            "Content-Length": f"{len(json.dumps(sp_avg_line))}",
            "X-RequestDigest": f"{self.get_form_digest_value()}",
        }
        response = requests.post(
            url=self.base_url
            + "sites/dmponline2avg/avg/_api/web/lists/GetByTitle(%27AVG%27)/items",
            headers=headers,
            json=sp_avg_line,
            auth=self.auth,
        )
        if response.status_code == 201:
            return True
        logger.error("Something went wrong. Status code: " + str(response.status_code))
        return False

    def update_avg_line(self, sp_avg_line, sp_avg_id):
        headers = {
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
            "Content-Length": f"{len(json.dumps(sp_avg_line))}",
            "X-RequestDigest": f"{self.get_form_digest_value()}",
            "If-Match": "*",  # * means overwrite regardless of version matching (OData standard)
            "X-HTTP-Method": "MERGE",
        }
        response = requests.post(
            url=self.base_url
            + f"sites/dmponline2avg/avg/_api/web/lists/GetByTitle(%27AVG%27)/items({sp_avg_id})",
            headers=headers,
            json=sp_avg_line,
            auth=self.auth,
        )
        if response.status_code == 200:
            return True
        logger.error("Something went wrong. Status code:" + str(response.status_code))
        return False

    def delete_avg_line(self, sp_avg_id):
        headers = {
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
            "X-RequestDigest": f"{self.get_form_digest_value()}",
            "If-Match": "*",  # * means overwrite regardless of version matching (OData standard)
            "X-HTTP-Method": "DELETE",
        }
        response = requests.post(
            url=self.base_url
            + f"sites/dmponline2avg/avg/_api/web/lists/GetByTitle(%27AVG%27)/items({sp_avg_id})",
            headers=headers,
            auth=self.auth,
        )
        if response.status_code == 200:
            return True
        logger.error("Something went wrong. Status code:" + str(response.status_code))
        return False


class ESBConnection:
    verify = True

    def __init__(
        self,
        token=settings.ESB_TOKEN,
        base_url=settings.ESB_URL,
        verify=settings.ESB_VERIFY,
    ):
        self.token = token
        self.base_url = base_url
        self.headers = {"Authorization": "Basic " + token, "Accept": "application/json"}
        if verify == "True":
            self.verify = True
        elif verify == "False":
            self.verify = False
        elif os.path.exists(verify):
            self.verify = verify

    def get_department(self, email_address):
        faculty, department = "", ""
        url = self.base_url + "faculty/get?emailAdres=" + email_address
        df = requests.get(url, headers=self.headers, verify=self.verify).json()
        try:
            if "organisatieEenheid" in df:
                elements = df["organisatieEenheid"]["afkortingNLVolledig"].split("-")
                faculty = elements[0]
                if len(elements) > 1:
                    department = elements[1]
            elif "faculteitId" in df:
                elements = df["faculteitId"].split()
                faculty = elements[0]
        except TypeError:
            pass
        except AttributeError:
            logger.error("DF" + str(df))
            pass
        return faculty, department

    def create_topdesk_ticket(self, esb_mappings):
        url = self.base_url + "storage/request/create"
        return requests.post(
            url, headers=self.headers, json=esb_mappings, verify=self.verify
        )


class AvgRegistry:
    def __init__(
        self,
        token=settings.AVG_REGISTRY_TOKEN,
        base_url=settings.AVG_REGISTRY_URL,
    ):
        self.token = token
        self.base_url = base_url
        self.verify = True
        self.headers = {
            "Authorization": "Token " + token,
            "Content-Type": "application/json",
        }

    def insert_record(self, record):
        return requests.post(
            url=self.base_url + "avgregisterline/external/",
            headers=self.headers,
            json=record,
            verify=self.verify,
        )

    def update_record(self, record, avg_id):
        return requests.put(
            url=self.base_url + f"avgregisterline/{avg_id}/",
            headers=self.headers,
            json=record,
            verify=self.verify,
        )

    def get_all(
        self,
    ):
        return requests.get(
            url=self.base_url + "externals/", headers=self.headers, verify=self.verify
        )

    def remove_record(self, dmp_id, avg_id):
        ext_deleted = requests.delete(
            self.base_url + f"externals/{dmp_id}/",
            headers=self.headers,
            verify=self.verify,
        )
        avg_deleted = requests.delete(
            self.base_url + f"avgregisterline/{avg_id}/",
            headers=self.headers,
            verify=self.verify,
        )
        return ext_deleted, avg_deleted


class Mappings:
    verify = True

    def __init__(
        self,
        token=settings.DMPONLINE_TOKEN,
        base_url=f"{settings.DMPONLINE_API_V0_URL}plans?plan=",
        v1=False,
        do_init=True,
        verify=settings.DMPONLINE_VERIFY,
    ):
        self.key_error_occurred = False
        self.v1 = v1
        self.token = token
        self.base_url = base_url
        self.plan = None
        self.jwt = ""
        if verify == "True":
            self.verify = True
        elif verify == "False":
            self.verify = False
        elif os.path.exists(verify):
            self.verify = verify
        if do_init:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            }
            params = {
                "grant_type": "authorization_code",
                "email": settings.DMPONLINE_USER_EMAIL,
                "code": self.token,
            }

            r = requests.post(
                settings.DMPONLINE_AUTH_URL,
                json=params,
                headers=headers,
                verify=self.verify,
            )

            self.jwt = r.json()[
                "access_token"
            ]  # for v1 auth, headers are different and contain jwt
            self.headers = {
                "Authorization": "Token token=" + token,
                "Content-Type": "application/json",
            }  # v1

    def get_start_end_date(self, plan_id):
        self.headers = {
            "Authorization": "Bearer " + self.jwt,
            "Content-Type": "application/json",
        }
        url = f"{settings.DMPONLINE_API_V1_URL}plans/{plan_id}"
        plan = requests.get(url, headers=self.headers, verify=self.verify).json()
        if plan["code"] == 200:
            plan = plan["items"][0]["dmp"]["project"][0]
            return plan["start"], plan["end"]
        return None, None

    def get_all_plan_ids(self):
        self.base_url = settings.DMPONLINE_API_V0_URL + "statistics/plans"
        result = requests.get(self.base_url, headers=self.headers, verify=self.verify)
        if result.status_code == 200:
            arr = []
            for item in result.json()["plans"]:
                if item["template"]["id"] in MAPPABLE_IDS and not item["test_plan"]:
                    arr.append(item["id"])
            return arr
        else:
            return False

    # this gets (max) 10 plans from DMPonline v0
    def get_page(self, page):
        self.base_url = f"{settings.DMPONLINE_API_V0_URL}plans?page={page}"
        return requests.get(
            self.base_url, headers=self.headers, verify=self.verify
        ).json()

    # gets one specific plan by id
    def set_plan(self, plan_id):
        self.plan = requests.get(
            self.base_url + str(plan_id), headers=self.headers, verify=self.verify
        ).json()[0]

    def set_plan_by_dict(self, plan):
        self.plan = plan

    # get selected options
    # args:
    # section (int)
    # question (int)
    # returns selected options in section:question (list of strings)
    def get_selected_options(self, section, question):
        selected_options = []
        if self.plan["plan_content"][0]["sections"][section]["questions"][question][
            "answered"
        ]:
            try:
                for option in self.plan["plan_content"][0]["sections"][section][
                    "questions"
                ][question]["answer"]["options"]:
                    selected_options.append(option["text"])
            except KeyError as e:
                logger.warning(
                    f"{self.get_id()}, [get_selected_options] Key error:, {section}, {question}"
                )
                logger.warning(inspect.stack()[1].function)
                self.key_error_occurred = True
                logger.warning(e)
                pass
        return selected_options

    def has_human_participants(self):  # section 4 question 7
        section = 4
        question = 0
        option = "Yes"
        if self.has_option_selected(section, question, option):
            return True
        option = "No"
        if self.has_option_selected(section, question, option):
            return False

    def has_personal_data(self):  # section 4 question 8A
        section = 4
        question = 1
        option = "Yes"
        if self.has_option_selected(section, question, option):
            return True
        option = "No"
        if self.has_option_selected(section, question, option):
            return False

    def has_confidential_data(self):  # section 4 question 8B
        section = 4
        question = 2
        option = "Yes"
        if self.has_option_selected(section, question, option):
            return True
        option = "No"
        if self.has_option_selected(section, question, option):
            return False

    # checks if specific option:section is ticked
    # returns boolean or None (some questions do not appear
    # in json)
    def has_option_selected(self, section, question, option_text):
        try:
            if (
                self.plan["plan_content"][0]["sections"][section]["questions"][
                    question
                ]["answered"]
                is True
                and self.plan["plan_content"][0]["sections"][section]["questions"][
                    question
                ]["option_based"]
                is True
            ):
                try:
                    for option in self.plan["plan_content"][0]["sections"][section][
                        "questions"
                    ][question]["answer"]["options"]:
                        if option["text"].startswith(option_text):
                            return True
                except KeyError as e:
                    logger.warning(
                        f"{self.get_id()}, [has_options_selected] Key Error:, {section}, {question}, {option_text}"
                    )
                    self.key_error_occurred = True
                    logger.warning(inspect.stack()[1].function)
                    logger.warning(e)
                    return False
                return False
        except IndexError:
            return

    def get_free_text(self, section, question):
        if self.plan["plan_content"][0]["sections"][section]["questions"][question][
            "answered"
        ]:
            return self.plan["plan_content"][0]["sections"][section]["questions"][
                question
            ]["answer"]["text"]
        return "-"

    # returns comma-separated string of countries involved or -
    def get_countries(self):  # section 4, question 13
        section = None
        question = None
        if self.get_template_id() == 975303870:
            section = 4
            question = 7
        elif self.get_template_id() in (1753695087, 1165855271):
            return "-"
        if self.plan["plan_content"][0]["sections"][section]["questions"][question][
            "answered"
        ]:
            try:
                options = self.plan["plan_content"][0]["sections"][section][
                    "questions"
                ][question]["answer"]["options"]

                options = [option["text"] for option in options]

                if "Other" in options:
                    options.append(
                        clean_html(
                            self.plan["plan_content"][0]["sections"][section][
                                "questions"
                            ][question]["answer"]["text"]
                        )
                    )
                return ", ".join(options)
            except KeyError:
                return "-"
        return "-"

    def get_duration_of_storage(self):
        option = None
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 4 question 23
            section = 4
            question = 17
            option = "10 years or more"
        elif self.get_template_id() == 1753695087:  # section 5 question 5.1
            section = 5
            question = 0
            option = "All data resulting"
        elif self.get_template_id() == 1165855271:
            return "-"
        if self.has_option_selected(section, question, "Other"):
            return self.plan["plan_content"][0]["sections"][section]["questions"][
                question
            ]["answer"]["text"]
        elif self.has_option_selected(section, question, option):
            return self.plan["plan_content"][0]["sections"][section]["questions"][
                question
            ]["answer"]["options"][0]["text"]
        return "-"

    # for now focus is on Delft 2021 template only
    def is_mappable(self):
        logger.info(f"Template ID {self.get_template_id()}")
        logger.info("Mappable: " + str(self.get_template_id() in MAPPABLE_IDS))
        return self.get_template_id() in MAPPABLE_IDS

    def get_id(self):
        return self.plan["id"]

    def get_title(self):
        return self.plan["title"]

    def get_template_id(self):
        return self.plan["template"]["id"]

    def get_template_name(self):
        return self.plan["template"]["title"]

    # plans have a 'z' at the end of datetime string for unclear reasons
    def get_last_updated(self):
        dt = datetime.strptime(self.plan["last_updated"], "%Y-%m-%d %H:%M:%S %Z")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    def is_test_plan(self):
        return self.plan["test_plan"]

    def get_abstract(self):
        return (
            self.plan["description"]
            if self.plan["description"] is not None
            and self.plan["description"].strip() != ""
            else "-"
        )

    # storage locations are either in an html table
    # and/or in a
    # specific question with checkboxes
    # returns ;-separated string of locations or - if None
    def get_storage_locations(self):
        locations = []
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 1, question 3
            section = 1
            question = 0
        elif self.get_template_id() == 1753695087:  # section 3, question 3.1
            section = 3
            question = 0
        elif self.get_template_id() == 1165855271:
            section = 0
            question = 2
        else:
            return "-"
        if self.plan["plan_content"][0]["sections"][section]["questions"][question][
            "answered"
        ]:
            answer = self.get_free_text(section, question)
            if self.get_template_id() == 975303870:
                try:
                    locations = [
                        row["Storage location"] for row in html_table_to_list(answer)
                    ]
                except KeyError:
                    locations = []
                except AttributeError:
                    locations = []

                section = 3
                question = 0
                if self.plan["plan_content"][0]["sections"][section]["questions"][
                    question
                ]["answered"]:
                    try:
                        for option in self.plan["plan_content"][0]["sections"][section][
                            "questions"
                        ][question]["answer"]["options"]:
                            locations.append(option["text"])
                    except KeyError as e:
                        logger.warning(
                            f"{self.get_id()}, [get_storage_locations] Key Error:, {section}, {question}"
                        )
                        logger.warning(inspect.stack()[1].function)
                        self.key_error_occurred = True
                        logger.warning(e)
                        pass

            elif self.get_template_id() == 1753695087:
                locations.append(answer)
                for option in self.plan["plan_content"][0]["sections"][section][
                    "questions"
                ][question]["answer"]["options"]:
                    locations.append(option["text"])
            elif self.get_template_id() == 1165855271:
                locations.append(answer)
                try:
                    for option in self.plan["plan_content"][0]["sections"][section][
                        "questions"
                    ][question]["answer"]["options"]:
                        locations.append(option["text"])
                except KeyError:
                    pass
            locations = remove_special_chars_from_list(locations)
            return ";".join(locations)
        return "-"

    # returns ;-separated string as set of strings
    def get_storage_locations_stats(self):
        locations = self.get_storage_locations()
        if locations != "-":
            locations = locations.split(";")
        return set(locations)

    # data sources are either in an html table
    # and/or in a specific question with checkboxes
    # returns ;-separated string of locations or - if None
    def get_data_sources(self):
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 1 question 3
            section = 1
            question = 0
        elif self.get_template_id() in (1753695087, 1165855271):
            return "-"
        if self.plan["plan_content"][0]["sections"][section]["questions"][question][
            "answered"
        ]:
            answer = self.plan["plan_content"][0]["sections"][section]["questions"][
                question
            ]["answer"]["text"]
            try:
                sources = [
                    row[
                        "How will data be collected (for re-used data: source and terms of use)?"
                    ]
                    for row in html_table_to_list(answer)
                ]
            except AttributeError:
                sources = []
            except KeyError:
                sources = []

            sources = remove_special_chars_from_list(sources)

            return ";".join(set(sources))
        return "-"

    def get_legal_ground(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 15
            section = 4
            question = 9
            option = "Informed consent"
        elif self.get_template_id() == 1753695087:
            return "-"
        elif self.get_template_id() == 1165855271:
            return "-"
        if self.has_option_selected(section, question, option):
            return option
        else:
            if self.plan["plan_content"][0]["sections"][section]["questions"][question][
                "answered"
            ]:
                return self.plan["plan_content"][0]["sections"][section]["questions"][
                    question
                ]["answer"]["text"]
        return "-"

    def get_owner(self):
        try:
            return self.plan["principal_investigator"]["name"]
        except KeyError as e:
            logger.warning(str(self.get_id()) + "[get_owner] Key Error:")
            logger.warning(inspect.stack()[1].function)
            self.key_error_occurred = True
            logger.warning(e)
            return "-"

    def get_owner_email(self):
        try:
            return self.plan["principal_investigator"]["email"]
        except KeyError as e:
            logger.warning(f"{self.get_id()}, [get_owner_email] Key Error:")
            logger.warning(inspect.stack()[1].function)
            self.key_error_occurred = True
            logger.warning(e)
            return None

    def has_special_categories(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Special categories of personal data"
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None

        return self.has_option_selected(section, question, option)

    def has_financial_info_iban(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Financial information"
        elif self.get_template_id() in (1753695087, 1165855271):
            return None
        return self.has_option_selected(section, question, option)

    def has_photo_material(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Photographs, video materials"
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None
        return self.has_option_selected(section, question, option)

    def has_names_and_addresses(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Names and addresses"
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None
        return self.has_option_selected(section, question, option)

    def has_gender_date_of_birth(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Gender, date of birth"
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None
        return self.has_option_selected(section, question, option)

    def has_place_of_birth_nationality_id(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Copies of passports"
        elif self.get_template_id() in (1753695087, 1165855271):
            return None
        return self.has_option_selected(section, question, option)

    def has_email_addresses(self):
        section = None
        question = None
        option = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
            option = "Email addresses"
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None
        return self.has_option_selected(section, question, option)

    def has_phone_numbers(self):
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None
        option = "Telephone numbers"
        return self.has_option_selected(section, question, option)

    def has_bsn(self):
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
        elif self.get_template_id() == 1753695087:
            return None
        elif self.get_template_id() == 1165855271:
            return None
        option = "Citizen Service Number"
        return self.has_option_selected(section, question, option)

    def has_study_or_employ_info(self):
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
        elif self.get_template_id() in (1753695087, 1165855271):
            return None
        option = "Access or identification details, such as personnel number"
        return self.has_option_selected(section, question, option)

    def has_personal_info(self):
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 4, question 8A
            section = 4
            question = 1
        elif self.get_template_id() == 1753695087:  # section 4, question 1
            section = 4
            question = 0
        elif self.get_template_id() == 1165855271:
            return (
                self.has_gender_date_of_birth()
                or self.has_photo_material()
                or self.has_names_and_addresses()
                or self.has_email_addresses()
            )
        option = "Yes"
        return self.has_option_selected(section, question, option)

    def get_storage_amount(self):
        if self.get_template_id() == 975303870:  # section 1, question 4
            section = 1
            question = 1
            if self.has_option_selected(section, question, "< 250 GB"):
                return "250 TB"
            if self.has_option_selected(section, question, "250 GB - 5 TB"):
                return "5 TB"
            if self.has_option_selected(section, question, "> 5 TB"):
                return "> 5 TB"

    def get_storage_amount_public(self):
        if self.get_template_id() == 975303870:  # section 5, question 30
            section = 5
            question = 4
            if self.has_option_selected(section, question, "< 100 GB"):
                return "100 GB"
            if self.has_option_selected(section, question, "100 GB - 1 TB"):
                return "1 TB"
            if self.has_option_selected(section, question, "> 1 TB"):
                return "> 1 TB"

    def get_data_types(self):
        types = []
        if self.get_template_id() == 975303870:  # section 5, question 20
            section = 5
            question = 0
            for data_type in self.get_selected_options(section, question):
                types.append(data_type)
            section = 5
            question = 1
            for data_type in self.get_selected_options(section, question):
                types.append(data_type)
        return types

    def get_share_types(self):
        types = []
        if self.get_template_id() == 975303870:  # section 5, question 29
            section = 5
            question = 2
            for t in self.get_selected_options(section, question):
                types.append(t)
            section = 5  # section 5, question 30
            question = 3
            for t in self.get_selected_options(section, question):
                types.append(t)
        return types

    def has_other_types_personal_info(self):
        section = None
        question = None
        if self.get_template_id() == 975303870:  # section 4, question 10
            section = 4
            question = 4
        elif self.get_template_id() in (1753695087, 1165855271):
            return "-"
        res = clean_html(self.get_free_text(section, question))
        return res if res != "" else "-"

    def has_dpia_executed(self):
        if (
            self.get_template_id() == 975303870
        ):  # section 4, question 13: DPIA is adviced
            section = 4
            question = 13
            option = "Yes"
            if self.has_option_selected(section, question, option):
                question = 14  # section 4, question 14:
                if (
                    self.get_free_text(section, question) != "-"
                ):  # non-empty outcome means yes
                    return True
                else:
                    return False

    def get_safety_measures(self):
        if self.get_template_id() == 975303870:  # section 4, question 14
            section = 4
            question = 8
            return self.get_free_text(section, question)

    def get_esb_mappings(self):
        start_date, stop_date = self.get_start_end_date(self.get_id())
        return {
            "DMPOnlineId": self.get_id(),
            "employeeResponsible": self.get_owner_email(),
            "secondResponsibleEmployee": self.get_owner_email(),
            "dataClassification": "Standard",
            "backupRetention": "Standard",
            "researchProjectName": self.get_title(),
            "driveName": self.get_storage_locations(),
            "initialDriveSpace": self.get_storage_amount(),
            "intendedDriveSpace": self.get_storage_amount(),
            "projectStartDate": start_date,
            "ProjectEndDate": stop_date,
            "usersTUD": {
                "userTUD": [
                    {"emailAddress": self.get_owner_email(), "access": "Read/Write"},
                ]
            },
            "usersExternal": {
                "userExternal": [
                    #      {
                    #         "firstname":"Koos",
                    #         "lastname":"Willemse",
                    #         "emailAddress":"K.Willemse@tue.nl",
                    #         "mobile":"+31612345678",
                    #         "organisation":"TU Eindhoven",
                    #         "dateBirth":"2001-05-15",
                    #         "dateStart":"2021-12-21",
                    #         "dateEnd":"2023-01-01",
                    #         "access":"Read"
                    #      },
                    #      {
                    #         "firstname":"Emma",
                    #         "lastname":"Jansen",
                    #         "emailAddress":"E.Jansen@tue.nl",
                    #         "mobile":"+31612345678",
                    #         "organisation":"TU Eindhoven",
                    #         "dateBirth":"2001-05-15",
                    #         "dateStart":"2021-12-21",
                    #         "dateEnd":"2023-01-01",
                    #         "access":"Read"
                    #      }
                ]
            },
        }

    def get_avg_mappings(self):
        return {
            "source": "DMPonline",
            "sourcekey": self.get_id(),
            "avgregisterline": {
                "verwerking": self.get_title(),
                "applicatienaam": "-",
                "naam_opslagmedium": self.get_storage_locations(),
                "doel_van_de_verwerking": self.get_abstract(),
                "rechtmatige_grondslag": self.get_legal_ground(),
                "opmerkingen": "-",
                "eigenaar": self.get_owner(),
                "beheerders": self.get_owner(),
                "betrokkenen": self.get_owner(),
                "inschatting_aantal_betrokkenen": "-",
                "registratie_van_NAW_gegevens": self.has_names_and_addresses(),
                "registratie_van_genderinformatie": self.has_gender_date_of_birth(),
                "registratie_van_geboortedatum": self.has_gender_date_of_birth(),
                "registratie_van_geboorteplaats": self.has_place_of_birth_nationality_id(),
                "registratie_van_nationaliteit": self.has_place_of_birth_nationality_id(),
                "registratie_van_IBAN_nummer": self.has_financial_info_iban(),
                "verwerking_van_foto": self.has_photo_material(),
                "registratie_van_emailadres": self.has_email_addresses(),
                "registratie_van_telefoonnummer": self.has_phone_numbers(),
                "registratie_van_identificatiebewijs": self.has_place_of_birth_nationality_id(),
                "registratie_van_BSN_nummer": self.has_bsn(),
                "registratie_van_studienummer": None,  # self.has_study_or_employ_info(),
                "registratie_van_personeelsnummer": None,  # self.has_study_or_employ_info(),
                "registratie_van_videobeeldinformatie": self.has_photo_material(),
                "registratie_van_geluidsinformatie": self.has_photo_material(),
                "registratie_van_locatie_informatie": None,  # ---- ?
                "registratie_van_financiële_informatie": self.has_financial_info_iban(),
                "registratie_van_burgerlijke_staat": None,  # ---- ?
                "registratie_van_gezinssamenstelling": None,  # ---- ?
                "registratie_van_lidmaatschap_van_een_vakbond": None,  # self.has_special_categories(),
                "registratie_van_strafrechtelijke_gegevens": None,  # self.has_special_categories(),
                "registratie_van_gezondheidsgegevens": None,  # self.has_special_categories(),
                "registratie_van_opleidingsinformatie": None,  # self.has_study_or_employ_info(),
                "registratie_van_functie_informatie": None,  # self.has_study_or_employ_info(),
                "registratie_van_seksuele_geaardheid": None,  # self.has_special_categories(),
                "registratie_van_politieke_voorkeur": None,  # self.has_special_categories(),
                "registratie_van_religie": None,  # self.has_special_categories(),
                "registratie_van_genetische_informatie": None,  # self.has_special_categories(),
                "registratie_van_biometrische_informatie": None,  # self.has_special_categories(),
                "andere_categorieën_persoonsgegevens": self.has_other_types_personal_info(),
                "naam_verwerker": self.get_owner(),
                "verwerkersovereenkomst": None,  # ---- ?
                "ontvangers": "-",  # ---- ?
                "in_welke_landen_worden_de_gegevens_verwerkt": self.get_countries(),
                "vestigingsland_van_de_verwerker": self.get_countries(),
                "bewaartermijn": self.get_duration_of_storage(),
                "beveiligingsmaatregelen_die_genomen_worden_om_de_gegevens_te_beveiligen": self.get_safety_measures(),
                "bron_waar_de_gegevens_worden_verkregen": self.get_data_sources(),
                "DPIA_uitgevoerd": self.has_dpia_executed(),
                "bevat_persoonsgegevens": self.has_personal_info(),
            },
        }

    def get_sp_avg_mappings(self):
        return {
            "__metadata": {"type": "SP.Data.AvgListItem"},
            "Title": self.get_title(),
            "Registratie_x0020_van_x0020_gend": "Ja"
            if self.has_gender_date_of_birth()
            else "Nee",
            "Doelgroep": {
                "__metadata": {"type": "Collection(Edm.String)"},
                "results": ["Medewerkers", "Studenten", "externen/gasten"],
            },
            "Registratie_x0020_van_x0020_IBAN": "Ja"
            if self.has_financial_info_iban()
            else "Nee",
            "Registratie_x0020_van_x0020_nati": "Ja"
            if self.has_place_of_birth_nationality_id()
            else "Nee",
            "Rechtmatige_x0020_grondslag": self.get_legal_ground(),
            "Registratie_x0020_van_x0020_gebo": "Ja"
            if self.has_gender_date_of_birth()
            else "Nee",
            "Sub_x002d_verwerkers_x0020__x002": self.get_countries(),
            "Beheerder": {
                "__metadata": {"type": "Collection(Edm.String)"},
                "results": [self.get_owner()],
            },
            "Eindverantwoordellijke": self.get_owner(),
            "Applicatie_x002d_eigenaar": self.get_owner(),
            "Registratie_x0020_van_x0020_NAW_": "Ja"
            if self.has_names_and_addresses()
            else "Nee",
            "Verwerking_x0020_van_x0020_foto": "Ja"
            if self.has_photo_material()
            else "Nee",
            "Registratie_x0020_van_x0020_e_x0": {
                "__metadata": {"type": "Collection(Edm.String)"},
                "results": ["Ja" if self.has_email_addresses() else "Nee"],
            },
            "Doelstelling_x0020__x0020_van_x0": self.get_abstract(),
            "Opmerkingen": "-",
            "Registratie_x0020_van_x0020_fina": "Ja"
            if self.has_financial_info_iban()
            else "Nee",
            "Registratie_x0020_van_x0020_fysi": "",
            "Registratie_x0020_van_x0020_psyc": "",
            "Registratie_x0020_van_x0020_vide": "Ja"
            if self.has_photo_material()
            else "Nee",
            "Registratie_x0020_van_x0020_BSN_": "Ja" if self.has_bsn() else "Nee",
            "Registratie_x0020_van_x0020_iden": "Ja"
            if self.has_place_of_birth_nationality_id()
            else "Nee",
            "Registratie_x0020_van_x0020_gelu": "Ja"
            if self.has_photo_material()
            else "Nee",
            "Registratie_x0020_van_x0020_loca": "",
            "Registratie_x0020_van_x0020_gezi": "",
            "Registratie_x0020_van_x0020_stud": "",
            "Registratie_x0020_van_x0020_pers": "Ja"
            if self.has_personal_info()
            else "Nee",
            "Registratie_x0020_van_x0020_tele": {
                "__metadata": {"type": "Collection(Edm.String)"},
                "results": ["Ja" if self.has_phone_numbers() else "Nee"],
            },
            "Registratie_x0020_van_x0020_lidm": "",
            "Registratie_x0020_van_x0020_gere": "",
            "Registratie_x0020_van_x0020_medi": "",
            "ApplicatienaamId": {
                "__metadata": {"type": "Collection(Edm.Int32)"},
                "results": [1],
            },
            "Registratie_x0020_van_x0020_gebo0": "Ja"
            if self.has_gender_date_of_birth()
            else "Nee",
            "Registratie_x0020_van_x0020_ople": "",
            "Registratie_x0020_van_x0020_func": "",
            "Registratie_x0020_van_x0020_sexu": "",
            "Registratie_x0020_van_x0020_poli": "",
            "Registratie_x0020_van_x0020_reli": "",
            "Registratie_x0020_van_x0020_gene": "",
            "Registratie_x0020_van_x0020_biom": "",
            "Registratie_x0020_van_x0020_de_x": "",
            "Verwerkingsovereenkomst": "",
            "Verwerkingssoort": "",
            "Bewaartermijn_x0020_van_x0020_de": self.get_duration_of_storage(),
            "Maatregelen_x0020_om_x0020_incid": self.get_safety_measures(),
            "Registratie_x0020_van_x0020_pers0": "Ja"
            if self.has_personal_info()
            else "Nee",
            "Herkomst_x0020_van_x0020_informa": self.get_data_sources(),
            "Inschatting_x0020_aantal_x0020_b": "",
            "Bevat_x0020_persoonsgegevens_x00": "Ja"
            if self.has_personal_info()
            else "Nee",
            "Indien_x0020_gegevens_x0020_word": "",
            "Eventueel_x0020_andere_x0020_cat": self.has_other_types_personal_info(),
            "Naam_x0020_verwerker_x0028_s_x00": self.get_owner(),
            "Rol_x0020_van_x0020_de_x0020_TU_": "",
            "Wat_x0020_is_x0020_het_x0020_ves": self.get_countries(),
            "Registratie_x0020_van_x0020_NetI": "",
            "Naam_x0020_opslagmedium": {
                "__metadata": {"type": "SP.Taxonomy.TaxonomyFieldValue"},
                "Label": "1",
                "TermGuid": "71a4eb18-6698-4712-8c82-df615bef9464",
                "WssId": 1,
            },
        }
