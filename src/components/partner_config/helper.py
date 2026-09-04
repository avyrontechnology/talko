from typing import Any, Dict, List, Optional, Union

from bson import ObjectId

from src.components.did_management.services import DidManagementService
from src.components.partner_config.dto import Contract
from src.components.partner_config.repository import PartnerConfigRepository
from src.components.vendor_config.repository import VendorConfigRepository
from src.components.vendor_config.services import VendorConfigService
from src.exceptions import BadRequestError, ConflictError
from src.loggers.holler_service_logger import HollerServiceLogger


class PartnerConfigHelper:
    @staticmethod
    async def validate_and_prepare_config(
        config: Contract.PartnerConfigCreate,
        vendor_config_validator: Any,
        partner_config_validator: Any,
        repository: PartnerConfigRepository,
        logger: HollerServiceLogger,
    ) -> ObjectId:
        """
        Validates the initial configuration and prepares the vendor ID.
        """
        try:
            vendor_id: ObjectId = ObjectId(config.vendor_id)
        except Exception:
            logger.error("Invalid vendor_id: {}".format(config.vendor_id))
            raise ValueError("Invalid vendor_id format.")

        logger.debug(
            "Partner config for partner_id {} with vendor_id: {}".format(
                config.partner_id, vendor_id
            )
        )
        await vendor_config_validator.validate_vendor_exists(vendor_id)
        await vendor_config_validator.validate_vendor_config_not_exist_using_vendor_id(
            vendor_id
        )
        await partner_config_validator.check_if_already_partner_exist_in_partner_config(
            config.partner_id
        )

        existing_config: Optional[Dict[str, Any]] = (
            await repository.find_partner_config_by_id(config.partner_id)
        )
        if existing_config:
            logger.error(
                "Partner config with partner_id {} already exists".format(
                    config.partner_id
                )
            )
            raise ConflictError("Partner config with partner_id already exists.")

        return vendor_id

    @staticmethod
    async def handle_did_assignment(
        config: Contract.PartnerConfigCreate,
        vendor_id: ObjectId,
        vendor_config_repository: VendorConfigRepository,
        vendor_config_service: VendorConfigService,
        did_management_service: DidManagementService,
        logger: HollerServiceLogger,
    ) -> Dict[str, Union[str, bool, List[str], Dict[str, List[str]], int]]:
        """
        Handles the assignment of DIDs based on configuration by updating existing records.
        """
        logger.info("In partner config creation, handle did assignment method started.")
        logger.debug(
            "In partner config creation, handle did assignment method, data: config: {}".format(
                config
            )
        )

        vendor_config_id: Optional[ObjectId] = ObjectId(config.vendor_config_id)

        available_dids: List[str] = await did_management_service.get_available_dids(
            vendor_id, vendor_config_id
        )
        if not available_dids:
            logger.warning("No available DIDs for vendor_id {}".format(vendor_id))
            return {"vendor_id": str(vendor_id), "is_active": True}

        num_dids: int = PartnerConfigHelper._calculate_num_dids(config)
        if len(available_dids) < num_dids:
            raise BadRequestError(
                "Insufficient available DIDs. Required: {}, Available: {}".format(
                    num_dids, len(available_dids)
                )
            )

        assigned_dids: List[str] = available_dids[:num_dids]
        config_dict: Dict[str, Any] = {"vendor_id": str(vendor_id), "is_active": True}

        if config.enable_service_board and config.board_did_counts:
            service_board_mapping: Dict[str, Any] = (
                await PartnerConfigHelper._assign_service_board_dids(
                    config,
                    assigned_dids,
                    vendor_id,
                    did_management_service,
                    logger,
                    vendor_config_id,
                )
            )
            config_dict.update(service_board_mapping)

        if config.enable_agent_mapping and config.agent_mapping_ids:
            agent_mapping_data: Dict[str, Any] = (
                await PartnerConfigHelper._assign_agent_mapping_dids(
                    config,
                    assigned_dids,
                    vendor_id,
                    did_management_service,
                    logger,
                    vendor_config_id,
                )
            )
            config_dict.update(agent_mapping_data)

        if config.enable_round_robin:
            round_robin_data: Dict[str, Any] = (
                await PartnerConfigHelper._assign_round_robin_dids(
                    config,
                    assigned_dids,
                    vendor_id,
                    did_management_service,
                    logger,
                    vendor_config_id,
                )
            )
            config_dict.update(round_robin_data)

        logger.debug(
            "In partner config creation, handle did assignment method ended, data: config: {}".format(
                config_dict
            )
        )
        return config_dict

    @staticmethod
    async def _assign_service_board_dids(
        config: Contract.PartnerConfigCreate,
        assigned_dids: List[str],
        vendor_id: ObjectId,
        did_management_service: DidManagementService,
        logger: HollerServiceLogger,
        vendor_config_id: Optional[ObjectId] = None,
    ) -> Dict[str, Any]:
        """
        Assigns DIDs for service board configurations.
        """
        service_board_mapping: Dict[int, List[str]] = {}
        start_idx: int = 0
        for board_id, count in config.board_did_counts.items():
            if count > 0:
                end_idx: int = start_idx + count
                dids: List[str] = assigned_dids[start_idx:end_idx]
                service_board_mapping[board_id] = dids
                for did in dids:
                    await did_management_service.update_did(
                        did_number=did,
                        vendor_id=str(vendor_id),
                        partner_id=config.partner_id,
                        service_board_id=int(board_id),
                        agent_id=None,
                        vendor_config_id=vendor_config_id,
                    )
                start_idx = end_idx
        return {
            "service_board_ids": config.service_board_ids,
            "board_did_counts": config.board_did_counts,
        }

    @staticmethod
    async def _assign_agent_mapping_dids(
        config: Contract.PartnerConfigCreate,
        assigned_dids: List[str],
        vendor_id: ObjectId,
        did_management_service: DidManagementService,
        logger: HollerServiceLogger,
        vendor_config_id: Optional[ObjectId] = None,
    ) -> Dict[str, Any]:
        """
        Assigns DIDs for agent mapping configurations.
        """
        start_idx: int = (
            len(assigned_dids)
            if config.enable_service_board and config.board_did_counts
            else 0
        )
        agent_mapping_dids: List[str] = assigned_dids[
            start_idx : start_idx + len(config.agent_mapping_ids)
        ]
        for agent_id, did in zip(config.agent_mapping_ids, agent_mapping_dids):
            await did_management_service.update_did(
                did_number=did,
                vendor_id=str(vendor_id),
                partner_id=config.partner_id,
                service_board_id=None,
                agent_id=agent_id,
                vendor_config_id=vendor_config_id,
            )
        return {"agent_mapping_ids": config.agent_mapping_ids}

    @staticmethod
    async def _assign_round_robin_dids(
        config: Contract.PartnerConfigCreate,
        assigned_dids: List[str],
        vendor_id: ObjectId,
        did_management_service: DidManagementService,
        logger: HollerServiceLogger,
        vendor_config_id: Optional[ObjectId] = None,
    ) -> Dict[str, Any]:
        """
        Assigns DIDs for round-robin configurations.
        """
        if config.enable_service_board:
            raise BadRequestError("Round-robin cannot be enabled with service board.")
        if not config.round_robin_did_count:
            raise BadRequestError(
                "round_robin_did_count is required when enable_round_robin is true."
            )

        start_idx: int = 0
        if config.enable_service_board and config.board_did_counts:
            start_idx += len(assigned_dids)
        if config.enable_agent_mapping and config.agent_mapping_ids:
            start_idx += len(assigned_dids)

        round_robin_dids: List[str] = assigned_dids[
            start_idx : start_idx + config.round_robin_did_count
        ]
        for did in round_robin_dids:
            await did_management_service.update_did(
                did_number=did,
                vendor_id=str(vendor_id),
                partner_id=config.partner_id,
                service_board_id=None,
                agent_id=None,
                vendor_config_id=vendor_config_id,
            )
        return {"round_robin_did_count": config.round_robin_did_count}

    @staticmethod
    def _calculate_num_dids(config: Contract.PartnerConfigCreate) -> int:
        """
        Calculates the total number of DIDs required internally.
        """
        num_dids: int = 0
        if config.enable_service_board and config.board_did_counts:
            num_dids += sum(config.board_did_counts.values())
        if config.enable_agent_mapping and config.agent_mapping_ids:
            num_dids += len(config.agent_mapping_ids)
        if config.enable_round_robin and config.round_robin_did_count:
            num_dids += config.round_robin_did_count
        return num_dids

    @staticmethod
    async def update_default_attendance(
        config: Contract.PartnerConfigCreate,
        vendor_id: ObjectId,
        did_management_service: DidManagementService,
        logger: HollerServiceLogger,
    ) -> Dict[str, Any]:
        """
        Update default attendance for service board or round-robin.

        Args:
            config (Contract.PartnerConfigCreate): Partner config data.
            vendor_id (ObjectId): Vendor ID.
            did_management_service (DidManagementService): Service to manage DIDs.
            logger (HollerServiceLogger): Logger for tracking events.

        Returns:
            Dict[str, Any]: Updated attendance data to merge into config_dict.
        """
        attendance_data = {}
        if config.enable_service_board and config.service_board_ids:
            service_default_attendance = {}
            for service_board_id in config.service_board_ids:
                dids = await did_management_service.get_dids_by_partner_service_board_and_vendor(
                    config.partner_id, service_board_id, str(vendor_id)
                )
                service_default_attendance[service_board_id] = [
                    {"phone_number": did["did_number"], "agent_id": did.get("agent_id")}
                    for did in dids
                ]
            attendance_data["service_default_attendance"] = service_default_attendance
        elif config.enable_round_robin and config.round_robin_did_count:
            dids = await did_management_service.get_dids_by_partner_and_vendor(
                config.partner_id, str(vendor_id)
            )
            round_robin_default_attendance = {
                "default": [
                    {"phone_number": did["did_number"], "agent_id": did.get("agent_id")}
                    for did in dids[: config.round_robin_did_count]
                ]
            }
            attendance_data["round_robin_default_attendance"] = (
                round_robin_default_attendance
            )

        logger.info(f"Updated default attendance: {attendance_data}")
        return attendance_data
