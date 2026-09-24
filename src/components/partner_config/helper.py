from typing import Any

from bson import ObjectId

from src.components.did_management.services import TalkoDidManagementService
from src.components.partner_config.dto import TalkoContract
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.components.vendor_config.services import TalkoVendorConfigService
from src.exceptions import TalkoBadRequestError, TalkoConflictError
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerConfigHelper:
    @staticmethod
    async def validate_and_prepare_config(
        config: TalkoContract.PartnerConfigCreate,
        vendor_config_validator: Any,
        partner_config_validator: Any,
        repository: TalkoPartnerConfigRepository,
        logger: TalkoServiceLogger,
        client_repository: Any | None = None,
    ) -> ObjectId:
        """
        Validates the initial configuration and prepares the vendor ID.
        """
        try:
            vendor_id: ObjectId = ObjectId(config.vendor_id)
        except Exception:
            logger.error(f"Invalid vendor_id: {config.vendor_id}")
            raise ValueError("Invalid vendor_id format.")

        client_id = getattr(config, "client_id", None)
        if client_id is not None:
            try:
                client_oid = ObjectId(client_id)
            except Exception:
                logger.error(f"Invalid client_id: {client_id}")
                raise ValueError("Invalid client_id format.")
            if client_repository is not None:
                client_doc = await client_repository.find_by_id(client_oid)
                if not client_doc:
                    raise ValueError("Client not found.")
                if client_doc.get("partner_id") != config.partner_id:
                    raise ValueError("Client does not belong to this partner.")

        logger.debug(f"Partner config for partner_id {config.partner_id} client_id {client_id} with vendor_id: {vendor_id}")
        await vendor_config_validator.validate_vendor_exists(vendor_id)
        await vendor_config_validator.validate_vendor_config_not_exist_using_vendor_id(vendor_id)
        await partner_config_validator.check_if_already_partner_exist_in_partner_config(
            config.partner_id, client_id
        )

        existing_config: dict[str, Any] | None = await repository.find_partner_config_by_partner_and_client(
            config.partner_id, client_id
        )
        if existing_config:
            logger.error(f"Partner config with partner_id {config.partner_id} client_id {client_id} already exists")
            raise TalkoConflictError("Partner config with partner_id already exists.")

        return vendor_id

    @staticmethod
    async def handle_did_assignment(
        config: TalkoContract.PartnerConfigCreate,
        vendor_id: ObjectId,
        vendor_config_repository: TalkoVendorConfigRepository,
        vendor_config_service: TalkoVendorConfigService,
        did_management_service: TalkoDidManagementService,
        logger: TalkoServiceLogger,
    ) -> dict[str, str | bool | list[str] | dict[str, list[str]] | int]:
        """
        Handles the assignment of DIDs based on configuration by updating existing records.
        """
        logger.info("In partner config creation, handle did assignment method started.")
        logger.debug(f"In partner config creation, handle did assignment method, data: config: {config}")

        vendor_config_id: ObjectId | None = ObjectId(config.vendor_config_id)

        available_dids: list[str] = await did_management_service.get_available_dids(vendor_id, vendor_config_id)
        if not available_dids:
            logger.warning(f"No available DIDs for vendor_id {vendor_id}")
            return {"vendor_id": str(vendor_id), "is_active": True}

        num_dids: int = TalkoPartnerConfigHelper._calculate_num_dids(config)
        if len(available_dids) < num_dids:
            raise TalkoBadRequestError(
                f"Insufficient available DIDs. Required: {num_dids}, Available: {len(available_dids)}"
            )

        assigned_dids: list[str] = available_dids[:num_dids]
        config_dict: dict[str, Any] = {"vendor_id": str(vendor_id), "is_active": True}

        if config.enable_workspace and config.workspace_did_counts:
            workspace_mapping: dict[str, Any] = await TalkoPartnerConfigHelper._assign_workspace_dids(
                config,
                assigned_dids,
                vendor_id,
                did_management_service,
                logger,
                vendor_config_id,
            )
            config_dict.update(workspace_mapping)

        if config.enable_agent_mapping and config.agent_mapping_ids:
            agent_mapping_data: dict[str, Any] = await TalkoPartnerConfigHelper._assign_agent_mapping_dids(
                config,
                assigned_dids,
                vendor_id,
                did_management_service,
                logger,
                vendor_config_id,
            )
            config_dict.update(agent_mapping_data)

        if config.enable_round_robin:
            round_robin_data: dict[str, Any] = await TalkoPartnerConfigHelper._assign_round_robin_dids(
                config,
                assigned_dids,
                vendor_id,
                did_management_service,
                logger,
                vendor_config_id,
            )
            config_dict.update(round_robin_data)

        logger.debug(f"In partner config creation, handle did assignment method ended, data: config: {config_dict}")
        return config_dict

    @staticmethod
    async def _assign_workspace_dids(
        config: TalkoContract.PartnerConfigCreate,
        assigned_dids: list[str],
        vendor_id: ObjectId,
        did_management_service: TalkoDidManagementService,
        logger: TalkoServiceLogger,
        vendor_config_id: ObjectId | None = None,
    ) -> dict[str, Any]:
        """
        Assigns DIDs for workspace configurations.
        """
        workspace_mapping: dict[int, list[str]] = {}
        start_idx: int = 0
        for workspace_id, count in config.workspace_did_counts.items():
            if count > 0:
                end_idx: int = start_idx + count
                dids: list[str] = assigned_dids[start_idx:end_idx]
                workspace_mapping[workspace_id] = dids
                for did in dids:
                    await did_management_service.update_did(
                        did_number=did,
                        vendor_id=str(vendor_id),
                        partner_id=config.partner_id,
                        workspace_id=int(workspace_id),
                        agent_id=None,
                        vendor_config_id=vendor_config_id,
                    )
                start_idx = end_idx
        return {
            "workspace_ids": config.workspace_ids,
            "workspace_did_counts": config.workspace_did_counts,
        }

    @staticmethod
    async def _assign_agent_mapping_dids(
        config: TalkoContract.PartnerConfigCreate,
        assigned_dids: list[str],
        vendor_id: ObjectId,
        did_management_service: TalkoDidManagementService,
        logger: TalkoServiceLogger,
        vendor_config_id: ObjectId | None = None,
    ) -> dict[str, Any]:
        """
        Assigns DIDs for agent mapping configurations.
        """
        start_idx: int = len(assigned_dids) if config.enable_workspace and config.workspace_did_counts else 0
        agent_mapping_dids: list[str] = assigned_dids[start_idx : start_idx + len(config.agent_mapping_ids)]
        for agent_id, did in zip(config.agent_mapping_ids, agent_mapping_dids, strict=True):
            await did_management_service.update_did(
                did_number=did,
                vendor_id=str(vendor_id),
                partner_id=config.partner_id,
                workspace_id=None,
                agent_id=agent_id,
                vendor_config_id=vendor_config_id,
            )
        return {"agent_mapping_ids": config.agent_mapping_ids}

    @staticmethod
    async def _assign_round_robin_dids(
        config: TalkoContract.PartnerConfigCreate,
        assigned_dids: list[str],
        vendor_id: ObjectId,
        did_management_service: TalkoDidManagementService,
        logger: TalkoServiceLogger,
        vendor_config_id: ObjectId | None = None,
    ) -> dict[str, Any]:
        """
        Assigns DIDs for round-robin configurations.
        """
        if config.enable_workspace:
            raise TalkoBadRequestError("Round-robin cannot be enabled with workspace.")
        if not config.round_robin_did_count:
            raise TalkoBadRequestError("round_robin_did_count is required when enable_round_robin is true.")

        start_idx: int = 0
        if config.enable_workspace and config.workspace_did_counts:
            start_idx += len(assigned_dids)
        if config.enable_agent_mapping and config.agent_mapping_ids:
            start_idx += len(assigned_dids)

        round_robin_dids: list[str] = assigned_dids[start_idx : start_idx + config.round_robin_did_count]
        for did in round_robin_dids:
            await did_management_service.update_did(
                did_number=did,
                vendor_id=str(vendor_id),
                partner_id=config.partner_id,
                workspace_id=None,
                agent_id=None,
                vendor_config_id=vendor_config_id,
            )
        return {"round_robin_did_count": config.round_robin_did_count}

    @staticmethod
    def _calculate_num_dids(config: TalkoContract.PartnerConfigCreate) -> int:
        """
        Calculates the total number of DIDs required internally.
        """
        num_dids: int = 0
        if config.enable_workspace and config.workspace_did_counts:
            num_dids += sum(config.workspace_did_counts.values())
        if config.enable_agent_mapping and config.agent_mapping_ids:
            num_dids += len(config.agent_mapping_ids)
        if config.enable_round_robin and config.round_robin_did_count:
            num_dids += config.round_robin_did_count
        return num_dids

    @staticmethod
    async def update_default_attendance(
        config: TalkoContract.PartnerConfigCreate,
        vendor_id: ObjectId,
        did_management_service: TalkoDidManagementService,
        logger: TalkoServiceLogger,
    ) -> dict[str, Any]:
        """
        Update default attendance for workspace or round-robin.

        Args:
            config (TalkoContract.PartnerConfigCreate): Partner config data.
            vendor_id (ObjectId): Vendor ID.
            did_management_service (TalkoDidManagementService): Service to manage DIDs.
            logger (TalkoServiceLogger): Logger for tracking events.

        Returns:
            Dict[str, Any]: Updated attendance data to merge into config_dict.
        """
        attendance_data = {}
        if config.enable_workspace and config.workspace_ids:
            service_default_attendance = {}
            for workspace_id in config.workspace_ids:
                dids = await did_management_service.get_dids_by_partner_workspace_and_vendor(
                    config.partner_id, workspace_id, str(vendor_id)
                )
                service_default_attendance[workspace_id] = [
                    {"phone_number": did["did_number"], "agent_id": did.get("agent_id")} for did in dids
                ]
            attendance_data["service_default_attendance"] = service_default_attendance
        elif config.enable_round_robin and config.round_robin_did_count:
            dids = await did_management_service.get_dids_by_partner_and_vendor(config.partner_id, str(vendor_id))
            round_robin_default_attendance = {
                "default": [
                    {"phone_number": did["did_number"], "agent_id": did.get("agent_id")}
                    for did in dids[: config.round_robin_did_count]
                ]
            }
            attendance_data["round_robin_default_attendance"] = round_robin_default_attendance

        logger.info(f"Updated default attendance: {attendance_data}")
        return attendance_data
