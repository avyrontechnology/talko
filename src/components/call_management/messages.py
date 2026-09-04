# tata tele & acefone call service
AGENT_NUMBER_IS_REQUIRED = "Agent number is required"
INVALID_PARAMETER = "Invalid parameters: {}"
UNEXPECTED_API_RESPONSE = "Unexpected response: {}"
CALL_PLACED_SUCCESSFULLY = "call placed successfully"
HANGUP_URL_HANDLER_NOT_CONFIGURED = "hangup_url_handler not configured in vendor config"
CALL_TRANSFERRED_SUCCESSFULLY = "call transferred successfully"
TRANSFER_URL_HANDLER_NOT_CONFIGURED = (
    "transfer_url_handler not configured in vendor config"
)

# call hangup
CALL_ID_REQUIRED_FOR_HANGUP = "call_id is required"
CALL_HANGUP_INITIATED = "Call hangup request sent successfully"
CALL_HANGUP_FAILED = "Call hangup failed"
UNEXPECTED_ERROR_HANGUP_CALL = "Unexpected error hanging up call"

# tata tele & acefone webhook
WEBHOOK_PAYLOAD_MISSING = "Webhook payload missing call_id or uuid."
CALL_ID_MUST_BE_PROVIDED = "'call_id or uuid' must be provided"
CDR_NOT_FOUND = "CDR not found"
FAILED_TO_UPDATE = "Failed to update CDR"

# service
UNSUPPORTED_VENDOR = "Unsupported vendor: {}"
PARTNER_CONFIG_NOT_FOUND = "Partner config for partner_id not found"
NO_VENDOR_ID_ASSIGNED_TO_PARTNER = "No vendor_id assigned to partner."
NO_DID_ASSIGNED_TO_PARTNER = "No DIDs assigned to partner."
VENDOR_CONFIG_FOR_VENDOR_ID_NOT_FOUND = "Vendor config for vendor id not found"
DID_NOT_ASSIGNED_TO_PARTNER = "DID not assigned to vendor."

# call management controllers
CALL_INITIATION_FAILED = "Call initiation failed"
SOMETHING_WENT_WRONG = "Something went wrong"
UNEXPECTED_ERROR_INITIATING_CALL = "Unexpected error initiating call"
CALL_TRANSFER_FAILED = "Call transfer failed"
UNEXPECTED_ERROR_TRANSFERRING_CALL = "Unexpected error transferring call"

# helper
NO_ASSIGNED_DID_AVAILABLE_TO_AGENT = "No assigned DID available for agent"
INVALID_PARTNER_CONFIGURATION = (
    "Invalid partner configuration: No DID assignment strategy enabled"
)
FAILED_TO_DECRYPT_LEAD_SECRET_AS_HEX = (
    "Failed to decrypt lead_secret as hex. Ensure it is a valid hex string."
)
NO_VALID_PHONE_NUMBER_FOUND_FOR_LEAD = "No valid phone number found for lead."
