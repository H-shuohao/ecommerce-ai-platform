import hashlib
import json

from services.commerce_service import CommerceService, commerce_service
from services.data_platform_service import DataPlatformService, data_platform_service
from services.data_release_repository import DataReleaseRepository, data_release_repository


class DataPublicationService:
    def __init__(
        self,
        platform: DataPlatformService = data_platform_service,
        repository: DataReleaseRepository = data_release_repository,
        commerce: CommerceService = commerce_service,
    ) -> None:
        self.platform = platform
        self.repository = repository
        self.commerce = commerce

    def publish_commerce(self):
        snapshot = self.platform._load_commerce_data()
        quality_report = self.platform.check_commerce_quality()
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        version_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        status = "published" if quality_report.failed_checks == 0 else "blocked"
        release = self.repository.record(
            dataset="commerce",
            version_hash=version_hash,
            quality_score=quality_report.quality_score,
            status=status,
            snapshot=snapshot,
        )
        if status == "published":
            self.commerce.replace_data(snapshot)
        return release.model_copy(update={"quality_report": quality_report})

    def activate_commerce_release(self, release_id: str):
        activated = self.repository.activate(release_id)
        if activated is None:
            raise KeyError("数据版本不存在")
        release, snapshot = activated
        self.commerce.replace_data(snapshot)
        return release


data_publication_service = DataPublicationService()
