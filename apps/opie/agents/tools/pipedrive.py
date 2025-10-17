import json
import requests
from os import getenv
from typing import Any, List, Optional, cast
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

class PipedriveTools(Toolkit):
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "pipedrive",
        nango_host: Optional[str] = None,
        nango_secret_key: Optional[str] = None,
        nango_connection: Optional[object] = None,
        **kwargs,
    ):
        self.connection_id = connection_id
        self.provider_config_key = provider_config_key
        self.nango_host = nango_host or getattr(settings, 'NANGO_HOST', 'https://nango.opie.sh')
        self.nango_secret_key = nango_secret_key or getattr(settings, 'NANGO_SECRET_KEY', None)
        self.nango_connection = nango_connection  # Store the connection object

        if not self.nango_secret_key:
            raise ValueError("NANGO_SECRET_KEY not configured.")

        super().__init__(name="pipedrive_tools", **kwargs)

        # Register the methods as Agno tools
        self.register(self.get_deals)
        self.register(self.get_deal)
        self.register(self.create_deal)
        self.register(self.update_deal)
        self.register(self.delete_deal)
        self.register(self.get_persons)
        self.register(self.get_person)
        self.register(self.create_person)
        self.register(self.update_person)
        self.register(self.delete_person)
        self.register(self.get_organizations)
        self.register(self.get_organization)
        self.register(self.create_organization)
        self.register(self.update_organization)
        self.register(self.delete_organization)
        self.register(self.get_pipelines)
        self.register(self.get_pipeline)
        self.register(self.get_stages)
        self.register(self.get_activities)
        self.register(self.get_activity)
        self.register(self.create_activity)
        self.register(self.update_activity)
        self.register(self.delete_activity)
        self.register(self.search)

    def _make_nango_request(self, method: str, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        """
        Make a request to Pipedrive via Nango proxy.

        :param method: HTTP method (GET, POST, PUT, DELETE, etc.)
        :param endpoint: Pipedrive API endpoint (without base URL)
        :param data: Request body data for POST/PUT requests
        :param params: Query parameters
        :return: Response data as dictionary
        """
        url = f"{self.nango_host}/proxy/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.nango_secret_key}",
            "Connection-Id": self.connection_id,
            "Provider-Config-Key": self.provider_config_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, params=params)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, params=params)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            # Handle empty responses (like 204 No Content)
            if response.status_code == 204 or not response.text.strip():
                return {}

            json_data = response.json()
            return json_data if json_data is not None else {}
        except requests.RequestException as e:
            logger.error(f"Nango proxy request failed: {e}")
            raise

    # ========== DEALS ==========

    def get_deals(self, status: str = "all_not_deleted", limit: int = 100, start: int = 0) -> str:
        """
        Get all deals from Pipedrive.

        :param status: Deal status filter (all_not_deleted, open, won, lost, deleted, all)
        :param limit: Maximum number of deals to return (max 500)
        :param start: Pagination start
        :return: A JSON string containing deal information
        """
        try:
            params = {
                "status": status,
                "limit": min(limit, 500),
                "start": start
            }

            response_data = self._make_nango_request("GET", "v1/deals", params=params)

            deals = response_data.get("data", [])
            if deals:
                log_debug(f"Retrieved {len(deals)} deals from Pipedrive")
                return json.dumps(deals)
            else:
                return json.dumps([])

        except Exception as e:
            logger.error(f"Error retrieving deals: {e}")
            return json.dumps([])

    def get_deal(self, deal_id: int) -> str:
        """
        Get a specific deal by ID.

        :param deal_id: The ID of the deal to retrieve
        :return: A JSON string containing deal details
        """
        try:
            response_data = self._make_nango_request("GET", f"v1/deals/{deal_id}")

            deal = response_data.get("data", {})
            log_debug(f"Retrieved deal {deal_id}")
            return json.dumps(deal)

        except Exception as e:
            logger.error(f"Error retrieving deal {deal_id}: {e}")
            return json.dumps({"error": str(e), "deal_id": deal_id})

    def create_deal(self, title: str, person_id: Optional[int] = None, org_id: Optional[int] = None,
                   value: Optional[float] = None, currency: Optional[str] = None,
                   stage_id: Optional[int] = None, status: Optional[str] = None,
                   expected_close_date: Optional[str] = None, **kwargs) -> str:
        """
        Create a new deal in Pipedrive.

        :param title: Deal title (required)
        :param person_id: ID of the person associated with the deal
        :param org_id: ID of the organization associated with the deal
        :param value: Deal value
        :param currency: Currency (3-letter code, e.g., USD, EUR)
        :param stage_id: ID of the stage this deal will be placed in
        :param status: Deal status (open, won, lost, deleted)
        :param expected_close_date: Expected close date (YYYY-MM-DD)
        :param kwargs: Additional deal fields
        :return: A JSON string with the created deal details
        """
        try:
            data = {"title": title}

            if person_id is not None:
                data["person_id"] = person_id
            if org_id is not None:
                data["org_id"] = org_id
            if value is not None:
                data["value"] = value
            if currency:
                data["currency"] = currency
            if stage_id is not None:
                data["stage_id"] = stage_id
            if status:
                data["status"] = status
            if expected_close_date:
                data["expected_close_date"] = expected_close_date

            # Add any additional fields
            data.update(kwargs)

            response_data = self._make_nango_request("POST", "v1/deals", data=data)

            deal = response_data.get("data", {})
            log_debug(f"Created deal: {title}")
            return json.dumps({
                "status": "success",
                "deal": deal
            })

        except Exception as e:
            logger.error(f"Error creating deal {title}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "title": title
            })

    def update_deal(self, deal_id: int, **kwargs) -> str:
        """
        Update a deal's properties.

        :param deal_id: The ID of the deal to update
        :param kwargs: Fields to update (e.g., title, value, stage_id, status)
        :return: A JSON string with the update result
        """
        try:
            response_data = self._make_nango_request("PUT", f"v1/deals/{deal_id}", data=kwargs)

            deal = response_data.get("data", {})
            log_debug(f"Updated deal {deal_id}")
            return json.dumps({
                "status": "success",
                "deal": deal
            })

        except Exception as e:
            logger.error(f"Error updating deal {deal_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "deal_id": deal_id
            })

    def delete_deal(self, deal_id: int) -> str:
        """
        Delete a deal.

        :param deal_id: The ID of the deal to delete
        :return: A JSON string with the deletion result
        """
        try:
            response_data = self._make_nango_request("DELETE", f"v1/deals/{deal_id}")

            log_debug(f"Deleted deal {deal_id}")
            return json.dumps({
                "status": "success",
                "message": f"Deal {deal_id} deleted successfully"
            })

        except Exception as e:
            logger.error(f"Error deleting deal {deal_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "deal_id": deal_id
            })

    # ========== PERSONS ==========

    def get_persons(self, limit: int = 100, start: int = 0) -> str:
        """
        Get all persons from Pipedrive.

        :param limit: Maximum number of persons to return (max 500)
        :param start: Pagination start
        :return: A JSON string containing person information
        """
        try:
            params = {
                "limit": min(limit, 500),
                "start": start
            }

            response_data = self._make_nango_request("GET", "v1/persons", params=params)

            persons = response_data.get("data", [])
            if persons:
                log_debug(f"Retrieved {len(persons)} persons from Pipedrive")
                return json.dumps(persons)
            else:
                return json.dumps([])

        except Exception as e:
            logger.error(f"Error retrieving persons: {e}")
            return json.dumps([])

    def get_person(self, person_id: int) -> str:
        """
        Get a specific person by ID.

        :param person_id: The ID of the person to retrieve
        :return: A JSON string containing person details
        """
        try:
            response_data = self._make_nango_request("GET", f"v1/persons/{person_id}")

            person = response_data.get("data", {})
            log_debug(f"Retrieved person {person_id}")
            return json.dumps(person)

        except Exception as e:
            logger.error(f"Error retrieving person {person_id}: {e}")
            return json.dumps({"error": str(e), "person_id": person_id})

    def create_person(self, name: str, email: Optional[List[str]] = None, phone: Optional[List[str]] = None,
                     org_id: Optional[int] = None, **kwargs) -> str:
        """
        Create a new person in Pipedrive.

        :param name: Person's name (required)
        :param email: List of email addresses
        :param phone: List of phone numbers
        :param org_id: ID of the organization this person belongs to
        :param kwargs: Additional person fields
        :return: A JSON string with the created person details
        """
        try:
            data = {"name": name}

            if email:
                data["email"] = email
            if phone:
                data["phone"] = phone
            if org_id is not None:
                data["org_id"] = org_id

            # Add any additional fields
            data.update(kwargs)

            response_data = self._make_nango_request("POST", "v1/persons", data=data)

            person = response_data.get("data", {})
            log_debug(f"Created person: {name}")
            return json.dumps({
                "status": "success",
                "person": person
            })

        except Exception as e:
            logger.error(f"Error creating person {name}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "name": name
            })

    def update_person(self, person_id: int, **kwargs) -> str:
        """
        Update a person's properties.

        :param person_id: The ID of the person to update
        :param kwargs: Fields to update (e.g., name, email, phone, org_id)
        :return: A JSON string with the update result
        """
        try:
            response_data = self._make_nango_request("PUT", f"v1/persons/{person_id}", data=kwargs)

            person = response_data.get("data", {})
            log_debug(f"Updated person {person_id}")
            return json.dumps({
                "status": "success",
                "person": person
            })

        except Exception as e:
            logger.error(f"Error updating person {person_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "person_id": person_id
            })

    def delete_person(self, person_id: int) -> str:
        """
        Delete a person.

        :param person_id: The ID of the person to delete
        :return: A JSON string with the deletion result
        """
        try:
            response_data = self._make_nango_request("DELETE", f"v1/persons/{person_id}")

            log_debug(f"Deleted person {person_id}")
            return json.dumps({
                "status": "success",
                "message": f"Person {person_id} deleted successfully"
            })

        except Exception as e:
            logger.error(f"Error deleting person {person_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "person_id": person_id
            })

    # ========== ORGANIZATIONS ==========

    def get_organizations(self, limit: int = 100, start: int = 0) -> str:
        """
        Get all organizations from Pipedrive.

        :param limit: Maximum number of organizations to return (max 500)
        :param start: Pagination start
        :return: A JSON string containing organization information
        """
        try:
            params = {
                "limit": min(limit, 500),
                "start": start
            }

            response_data = self._make_nango_request("GET", "v1/organizations", params=params)

            orgs = response_data.get("data", [])
            if orgs:
                log_debug(f"Retrieved {len(orgs)} organizations from Pipedrive")
                return json.dumps(orgs)
            else:
                return json.dumps([])

        except Exception as e:
            logger.error(f"Error retrieving organizations: {e}")
            return json.dumps([])

    def get_organization(self, org_id: int) -> str:
        """
        Get a specific organization by ID.

        :param org_id: The ID of the organization to retrieve
        :return: A JSON string containing organization details
        """
        try:
            response_data = self._make_nango_request("GET", f"v1/organizations/{org_id}")

            org = response_data.get("data", {})
            log_debug(f"Retrieved organization {org_id}")
            return json.dumps(org)

        except Exception as e:
            logger.error(f"Error retrieving organization {org_id}: {e}")
            return json.dumps({"error": str(e), "org_id": org_id})

    def create_organization(self, name: str, **kwargs) -> str:
        """
        Create a new organization in Pipedrive.

        :param name: Organization name (required)
        :param kwargs: Additional organization fields (e.g., address, visible_to)
        :return: A JSON string with the created organization details
        """
        try:
            data = {"name": name}
            data.update(kwargs)

            response_data = self._make_nango_request("POST", "v1/organizations", data=data)

            org = response_data.get("data", {})
            log_debug(f"Created organization: {name}")
            return json.dumps({
                "status": "success",
                "organization": org
            })

        except Exception as e:
            logger.error(f"Error creating organization {name}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "name": name
            })

    def update_organization(self, org_id: int, **kwargs) -> str:
        """
        Update an organization's properties.

        :param org_id: The ID of the organization to update
        :param kwargs: Fields to update (e.g., name, address)
        :return: A JSON string with the update result
        """
        try:
            response_data = self._make_nango_request("PUT", f"v1/organizations/{org_id}", data=kwargs)

            org = response_data.get("data", {})
            log_debug(f"Updated organization {org_id}")
            return json.dumps({
                "status": "success",
                "organization": org
            })

        except Exception as e:
            logger.error(f"Error updating organization {org_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "org_id": org_id
            })

    def delete_organization(self, org_id: int) -> str:
        """
        Delete an organization.

        :param org_id: The ID of the organization to delete
        :return: A JSON string with the deletion result
        """
        try:
            response_data = self._make_nango_request("DELETE", f"v1/organizations/{org_id}")

            log_debug(f"Deleted organization {org_id}")
            return json.dumps({
                "status": "success",
                "message": f"Organization {org_id} deleted successfully"
            })

        except Exception as e:
            logger.error(f"Error deleting organization {org_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "org_id": org_id
            })

    # ========== PIPELINES & STAGES ==========

    def get_pipelines(self) -> str:
        """
        Get all pipelines from Pipedrive.

        :return: A JSON string containing pipeline information
        """
        try:
            response_data = self._make_nango_request("GET", "v1/pipelines")

            pipelines = response_data.get("data", [])
            log_debug(f"Retrieved {len(pipelines)} pipelines from Pipedrive")
            return json.dumps(pipelines)

        except Exception as e:
            logger.error(f"Error retrieving pipelines: {e}")
            return json.dumps([])

    def get_pipeline(self, pipeline_id: int) -> str:
        """
        Get a specific pipeline by ID.

        :param pipeline_id: The ID of the pipeline to retrieve
        :return: A JSON string containing pipeline details
        """
        try:
            response_data = self._make_nango_request("GET", f"v1/pipelines/{pipeline_id}")

            pipeline = response_data.get("data", {})
            log_debug(f"Retrieved pipeline {pipeline_id}")
            return json.dumps(pipeline)

        except Exception as e:
            logger.error(f"Error retrieving pipeline {pipeline_id}: {e}")
            return json.dumps({"error": str(e), "pipeline_id": pipeline_id})

    def get_stages(self, pipeline_id: Optional[int] = None) -> str:
        """
        Get all stages from Pipedrive, optionally filtered by pipeline.

        :param pipeline_id: Optional pipeline ID to filter stages
        :return: A JSON string containing stage information
        """
        try:
            params = {}
            if pipeline_id is not None:
                params["pipeline_id"] = pipeline_id

            response_data = self._make_nango_request("GET", "v1/stages", params=params)

            stages = response_data.get("data", [])
            log_debug(f"Retrieved {len(stages)} stages from Pipedrive")
            return json.dumps(stages)

        except Exception as e:
            logger.error(f"Error retrieving stages: {e}")
            return json.dumps([])

    # ========== ACTIVITIES ==========

    def get_activities(self, user_id: Optional[int] = None, deal_id: Optional[int] = None,
                      person_id: Optional[int] = None, org_id: Optional[int] = None,
                      type: Optional[str] = None, start: int = 0, limit: int = 100) -> str:
        """
        Get activities from Pipedrive with optional filters.

        :param user_id: Filter by user ID
        :param deal_id: Filter by deal ID
        :param person_id: Filter by person ID
        :param org_id: Filter by organization ID
        :param type: Filter by activity type
        :param start: Pagination start
        :param limit: Maximum number of activities to return (max 500)
        :return: A JSON string containing activity information
        """
        try:
            params = {
                "start": start,
                "limit": min(limit, 500)
            }

            if user_id is not None:
                params["user_id"] = user_id
            if deal_id is not None:
                params["deal_id"] = deal_id
            if person_id is not None:
                params["person_id"] = person_id
            if org_id is not None:
                params["org_id"] = org_id
            if type:
                params["type"] = type

            response_data = self._make_nango_request("GET", "v1/activities", params=params)

            activities = response_data.get("data", [])
            if activities:
                log_debug(f"Retrieved {len(activities)} activities from Pipedrive")
                return json.dumps(activities)
            else:
                return json.dumps([])

        except Exception as e:
            logger.error(f"Error retrieving activities: {e}")
            return json.dumps([])

    def get_activity(self, activity_id: int) -> str:
        """
        Get a specific activity by ID.

        :param activity_id: The ID of the activity to retrieve
        :return: A JSON string containing activity details
        """
        try:
            response_data = self._make_nango_request("GET", f"v1/activities/{activity_id}")

            activity = response_data.get("data", {})
            log_debug(f"Retrieved activity {activity_id}")
            return json.dumps(activity)

        except Exception as e:
            logger.error(f"Error retrieving activity {activity_id}: {e}")
            return json.dumps({"error": str(e), "activity_id": activity_id})

    def create_activity(self, subject: str, type: str, due_date: Optional[str] = None,
                       due_time: Optional[str] = None, duration: Optional[str] = None,
                       deal_id: Optional[int] = None, person_id: Optional[int] = None,
                       org_id: Optional[int] = None, note: Optional[str] = None, **kwargs) -> str:
        """
        Create a new activity in Pipedrive.

        :param subject: Activity subject (required)
        :param type: Activity type (required, e.g., call, meeting, task, deadline, email, lunch)
        :param due_date: Due date (YYYY-MM-DD)
        :param due_time: Due time (HH:MM)
        :param duration: Duration (HH:MM)
        :param deal_id: ID of the deal this activity is associated with
        :param person_id: ID of the person this activity is associated with
        :param org_id: ID of the organization this activity is associated with
        :param note: Note content
        :param kwargs: Additional activity fields
        :return: A JSON string with the created activity details
        """
        try:
            data = {
                "subject": subject,
                "type": type
            }

            if due_date:
                data["due_date"] = due_date
            if due_time:
                data["due_time"] = due_time
            if duration:
                data["duration"] = duration
            if deal_id is not None:
                data["deal_id"] = deal_id
            if person_id is not None:
                data["person_id"] = person_id
            if org_id is not None:
                data["org_id"] = org_id
            if note:
                data["note"] = note

            # Add any additional fields
            data.update(kwargs)

            response_data = self._make_nango_request("POST", "v1/activities", data=data)

            activity = response_data.get("data", {})
            log_debug(f"Created activity: {subject}")
            return json.dumps({
                "status": "success",
                "activity": activity
            })

        except Exception as e:
            logger.error(f"Error creating activity {subject}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "subject": subject
            })

    def update_activity(self, activity_id: int, **kwargs) -> str:
        """
        Update an activity's properties.

        :param activity_id: The ID of the activity to update
        :param kwargs: Fields to update (e.g., subject, type, due_date, done)
        :return: A JSON string with the update result
        """
        try:
            response_data = self._make_nango_request("PUT", f"v1/activities/{activity_id}", data=kwargs)

            activity = response_data.get("data", {})
            log_debug(f"Updated activity {activity_id}")
            return json.dumps({
                "status": "success",
                "activity": activity
            })

        except Exception as e:
            logger.error(f"Error updating activity {activity_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "activity_id": activity_id
            })

    def delete_activity(self, activity_id: int) -> str:
        """
        Delete an activity.

        :param activity_id: The ID of the activity to delete
        :return: A JSON string with the deletion result
        """
        try:
            response_data = self._make_nango_request("DELETE", f"v1/activities/{activity_id}")

            log_debug(f"Deleted activity {activity_id}")
            return json.dumps({
                "status": "success",
                "message": f"Activity {activity_id} deleted successfully"
            })

        except Exception as e:
            logger.error(f"Error deleting activity {activity_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "activity_id": activity_id
            })

    # ========== SEARCH ==========

    def search(self, term: str, item_types: Optional[List[str]] = None, limit: int = 100) -> str:
        """
        Search across Pipedrive for deals, persons, organizations, products, etc.

        :param term: Search term
        :param item_types: Optional list of item types to search (deal, person, organization, product, file)
        :param limit: Maximum number of results to return (max 500)
        :return: A JSON string containing search results
        """
        try:
            params = {
                "term": term,
                "limit": min(limit, 500)
            }

            if item_types:
                params["item_types"] = ",".join(item_types)

            response_data = self._make_nango_request("GET", "v1/itemSearch", params=params)

            results = response_data.get("data", {}).get("items", [])
            log_debug(f"Search for '{term}' returned {len(results)} results")
            return json.dumps(results)

        except Exception as e:
            logger.error(f"Error searching for '{term}': {e}")
            return json.dumps([])
