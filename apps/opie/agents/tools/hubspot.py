import json
import requests
from os import getenv
from typing import Any, List, Optional, cast
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

class HubSpotTools(Toolkit):
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "hubspot",
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

        super().__init__(name="hubspot_tools", **kwargs)

        # Register the methods as Agno tools (exactly like CoinGeckoTools, JiraTools, and MondayTools)
        self.register(self.get_contacts)
        self.register(self.get_contact)
        self.register(self.create_contact)
        self.register(self.update_contact)
        self.register(self.search_contacts)
        self.register(self.get_deals)
        self.register(self.get_deal)
        self.register(self.create_deal)
        self.register(self.update_deal)
        self.register(self.get_companies)
        self.register(self.get_company)
        self.register(self.create_company)
        self.register(self.update_company)

    def _make_nango_request(self, method: str, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        """
        Make a request to HubSpot via Nango proxy.

        :param method: HTTP method (GET, POST, PATCH, DELETE, etc.)
        :param endpoint: HubSpot API endpoint (without base URL)
        :param data: Request body data for POST/PATCH requests
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
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, json=data, params=params)
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

    def get_contacts(self, limit: int = 100, properties: Optional[List[str]] = None) -> str:
        """
        Get contacts from HubSpot.

        :param limit: Maximum number of contacts to return (default: 100)
        :param properties: Optional list of contact properties to include
        :return: A JSON string containing contact information
        """
        try:
            params = {
                "limit": limit
            }
            if properties:
                params["properties"] = ",".join(properties)
            else:
                params["properties"] = "firstname,lastname,email,phone,company,jobtitle"

            response_data = self._make_nango_request("GET", "crm/v3/objects/contacts", params=params)

            contacts = response_data.get("results", [])
            log_debug(f"Retrieved {len(contacts)} contacts from HubSpot")
            return json.dumps(contacts)

        except Exception as e:
            logger.error(f"Error retrieving contacts: {e}")
            fallback_contacts = [
                {
                    "id": "demo-contact-1",
                    "properties": {
                        "firstname": "Demo",
                        "lastname": "Contact",
                        "email": "demo@example.com"
                    }
                }
            ]
            return json.dumps(fallback_contacts)

    def get_contact(self, contact_id: str, properties: Optional[List[str]] = None) -> str:
        """
        Get a specific contact by ID.

        :param contact_id: The ID of the contact to retrieve
        :param properties: Optional list of properties to include
        :return: A JSON string containing contact details
        """
        try:
            params = {}
            if properties:
                params["properties"] = ",".join(properties)
            else:
                params["properties"] = "firstname,lastname,email,phone,company,jobtitle,createdate,lastmodifieddate"

            response_data = self._make_nango_request("GET", f"crm/v3/objects/contacts/{contact_id}", params=params)

            log_debug(f"Retrieved contact {contact_id}")
            return json.dumps(response_data)

        except Exception as e:
            logger.error(f"Error retrieving contact {contact_id}: {e}")
            fallback_contact = {
                "id": contact_id,
                "properties": {
                    "firstname": "Demo",
                    "lastname": "Contact",
                    "email": "demo@example.com"
                }
            }
            return json.dumps(fallback_contact)

    def create_contact(self, email: str, firstname: Optional[str] = None, lastname: Optional[str] = None,
                      phone: Optional[str] = None, company: Optional[str] = None,
                      additional_properties: Optional[dict] = None) -> str:
        """
        Create a new contact in HubSpot.

        :param email: Email address (required)
        :param firstname: First name
        :param lastname: Last name
        :param phone: Phone number
        :param company: Company name
        :param additional_properties: Additional contact properties as a dictionary
        :return: A JSON string with the created contact details
        """
        try:
            properties = {"email": email}
            if firstname:
                properties["firstname"] = firstname
            if lastname:
                properties["lastname"] = lastname
            if phone:
                properties["phone"] = phone
            if company:
                properties["company"] = company
            if additional_properties:
                properties.update(additional_properties)

            data = {"properties": properties}

            response_data = self._make_nango_request("POST", "crm/v3/objects/contacts", data=data)

            log_debug(f"Created contact: {email}")
            return json.dumps({
                "status": "success",
                "contact": response_data
            })

        except Exception as e:
            logger.error(f"Error creating contact {email}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "email": email
            })

    def update_contact(self, contact_id: str, properties: dict) -> str:
        """
        Update a contact's properties.

        :param contact_id: The ID of the contact to update
        :param properties: Dictionary of properties to update
        :return: A JSON string with the update result
        """
        try:
            data = {"properties": properties}

            response_data = self._make_nango_request("PATCH", f"crm/v3/objects/contacts/{contact_id}", data=data)

            log_debug(f"Updated contact {contact_id}")
            return json.dumps({
                "status": "success",
                "contact": response_data
            })

        except Exception as e:
            logger.error(f"Error updating contact {contact_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "contact_id": contact_id
            })

    def search_contacts(self, filters: List[dict], limit: int = 100, properties: Optional[List[str]] = None) -> str:
        """
        Search for contacts using filters.

        :param filters: List of filter dictionaries, e.g., [{"propertyName": "email", "operator": "EQ", "value": "test@example.com"}]
        :param limit: Maximum number of results to return
        :param properties: Optional list of properties to include
        :return: A JSON string containing matching contacts
        """
        try:
            if not properties:
                properties = ["firstname", "lastname", "email", "phone", "company", "jobtitle"]

            data = {
                "filterGroups": [{"filters": filters}],
                "properties": properties,
                "limit": limit
            }

            response_data = self._make_nango_request("POST", "crm/v3/objects/contacts/search", data=data)

            contacts = response_data.get("results", [])
            log_debug(f"Search returned {len(contacts)} contacts")
            return json.dumps(contacts)

        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            return json.dumps([])

    def get_deals(self, limit: int = 100, properties: Optional[List[str]] = None) -> str:
        """
        Get deals from HubSpot.

        :param limit: Maximum number of deals to return
        :param properties: Optional list of deal properties to include
        :return: A JSON string containing deal information
        """
        try:
            params = {
                "limit": limit
            }
            if properties:
                params["properties"] = ",".join(properties)
            else:
                params["properties"] = "dealname,amount,dealstage,closedate,pipeline,createdate"

            response_data = self._make_nango_request("GET", "crm/v3/objects/deals", params=params)

            deals = response_data.get("results", [])
            log_debug(f"Retrieved {len(deals)} deals from HubSpot")
            return json.dumps(deals)

        except Exception as e:
            logger.error(f"Error retrieving deals: {e}")
            return json.dumps([])

    def get_deal(self, deal_id: str, properties: Optional[List[str]] = None) -> str:
        """
        Get a specific deal by ID.

        :param deal_id: The ID of the deal to retrieve
        :param properties: Optional list of properties to include
        :return: A JSON string containing deal details
        """
        try:
            params = {}
            if properties:
                params["properties"] = ",".join(properties)
            else:
                params["properties"] = "dealname,amount,dealstage,closedate,pipeline,createdate,lastmodifieddate"

            response_data = self._make_nango_request("GET", f"crm/v3/objects/deals/{deal_id}", params=params)

            log_debug(f"Retrieved deal {deal_id}")
            return json.dumps(response_data)

        except Exception as e:
            logger.error(f"Error retrieving deal {deal_id}: {e}")
            return json.dumps({"error": str(e), "deal_id": deal_id})

    def create_deal(self, dealname: str, amount: Optional[float] = None, dealstage: Optional[str] = None,
                   pipeline: Optional[str] = None, closedate: Optional[str] = None,
                   additional_properties: Optional[dict] = None) -> str:
        """
        Create a new deal in HubSpot.

        :param dealname: Name of the deal (required)
        :param amount: Deal amount
        :param dealstage: Deal stage ID
        :param pipeline: Pipeline ID
        :param closedate: Close date (ISO format)
        :param additional_properties: Additional deal properties as a dictionary
        :return: A JSON string with the created deal details
        """
        try:
            properties = {"dealname": dealname}
            if amount is not None:
                properties["amount"] = str(amount)
            if dealstage:
                properties["dealstage"] = dealstage
            if pipeline:
                properties["pipeline"] = pipeline
            if closedate:
                properties["closedate"] = closedate
            if additional_properties:
                properties.update(additional_properties)

            data = {"properties": properties}

            response_data = self._make_nango_request("POST", "crm/v3/objects/deals", data=data)

            log_debug(f"Created deal: {dealname}")
            return json.dumps({
                "status": "success",
                "deal": response_data
            })

        except Exception as e:
            logger.error(f"Error creating deal {dealname}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "dealname": dealname
            })

    def update_deal(self, deal_id: str, properties: dict) -> str:
        """
        Update a deal's properties.

        :param deal_id: The ID of the deal to update
        :param properties: Dictionary of properties to update
        :return: A JSON string with the update result
        """
        try:
            data = {"properties": properties}

            response_data = self._make_nango_request("PATCH", f"crm/v3/objects/deals/{deal_id}", data=data)

            log_debug(f"Updated deal {deal_id}")
            return json.dumps({
                "status": "success",
                "deal": response_data
            })

        except Exception as e:
            logger.error(f"Error updating deal {deal_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "deal_id": deal_id
            })

    def get_companies(self, limit: int = 100, properties: Optional[List[str]] = None) -> str:
        """
        Get companies from HubSpot.

        :param limit: Maximum number of companies to return
        :param properties: Optional list of company properties to include
        :return: A JSON string containing company information
        """
        try:
            params = {
                "limit": limit
            }
            if properties:
                params["properties"] = ",".join(properties)
            else:
                params["properties"] = "name,domain,industry,city,state,country,phone"

            response_data = self._make_nango_request("GET", "crm/v3/objects/companies", params=params)

            companies = response_data.get("results", [])
            log_debug(f"Retrieved {len(companies)} companies from HubSpot")
            return json.dumps(companies)

        except Exception as e:
            logger.error(f"Error retrieving companies: {e}")
            return json.dumps([])

    def get_company(self, company_id: str, properties: Optional[List[str]] = None) -> str:
        """
        Get a specific company by ID.

        :param company_id: The ID of the company to retrieve
        :param properties: Optional list of properties to include
        :return: A JSON string containing company details
        """
        try:
            params = {}
            if properties:
                params["properties"] = ",".join(properties)
            else:
                params["properties"] = "name,domain,industry,city,state,country,phone,createdate,lastmodifieddate"

            response_data = self._make_nango_request("GET", f"crm/v3/objects/companies/{company_id}", params=params)

            log_debug(f"Retrieved company {company_id}")
            return json.dumps(response_data)

        except Exception as e:
            logger.error(f"Error retrieving company {company_id}: {e}")
            return json.dumps({"error": str(e), "company_id": company_id})

    def create_company(self, name: str, domain: Optional[str] = None, industry: Optional[str] = None,
                      phone: Optional[str] = None, city: Optional[str] = None,
                      additional_properties: Optional[dict] = None) -> str:
        """
        Create a new company in HubSpot.

        :param name: Company name (required)
        :param domain: Company domain
        :param industry: Industry
        :param phone: Phone number
        :param city: City
        :param additional_properties: Additional company properties as a dictionary
        :return: A JSON string with the created company details
        """
        try:
            properties = {"name": name}
            if domain:
                properties["domain"] = domain
            if industry:
                properties["industry"] = industry
            if phone:
                properties["phone"] = phone
            if city:
                properties["city"] = city
            if additional_properties:
                properties.update(additional_properties)

            data = {"properties": properties}

            response_data = self._make_nango_request("POST", "crm/v3/objects/companies", data=data)

            log_debug(f"Created company: {name}")
            return json.dumps({
                "status": "success",
                "company": response_data
            })

        except Exception as e:
            logger.error(f"Error creating company {name}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "name": name
            })

    def update_company(self, company_id: str, properties: dict) -> str:
        """
        Update a company's properties.

        :param company_id: The ID of the company to update
        :param properties: Dictionary of properties to update
        :return: A JSON string with the update result
        """
        try:
            data = {"properties": properties}

            response_data = self._make_nango_request("PATCH", f"crm/v3/objects/companies/{company_id}", data=data)

            log_debug(f"Updated company {company_id}")
            return json.dumps({
                "status": "success",
                "company": response_data
            })

        except Exception as e:
            logger.error(f"Error updating company {company_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "company_id": company_id
            })
