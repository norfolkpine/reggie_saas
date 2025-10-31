# Compliance Integrations

This document outlines the plan for integrating third-party services for KYC (Know Your Customer) and AML (Anti-Money Laundering) checks.

## Sumsub

*   **Service**: Identity verification, KYC, and AML.
*   **Use Case**: Verify the identity of individuals by checking their documents (passports, driver's licenses) and running them against global watchlists.
*   **Integration Plan**:
    *   Create a service in the `compliance` app to communicate with the Sumsub API.
    *   Initiate a verification check for a `Person` from the Django admin or via an API endpoint.
    *   Store the verification status and results on the `Person` model.
    *   Use webhooks from Sumsub to receive real-time updates on the verification process.

## GreenID

*   **Service**: Identity verification.
*   **Use Case**: Alternative or secondary provider for identity verification.
*   **Integration Plan**:
    *   Similar to Sumsub, create a dedicated service to handle API communication.
    *   The system should be designed to be provider-agnostic, allowing for the easy addition of new verification services like GreenID in the future.
