"""Domain-level exceptions."""


class DomainError(Exception):
    """Base for all domain errors."""


class VideoSourceNotFoundError(DomainError):
    pass


class ROIConfigNotFoundError(DomainError):
    pass


class InvalidROIConfigError(DomainError):
    pass


class AnalysisSessionNotFoundError(DomainError):
    pass


class InvalidVehicleTypeError(DomainError):
    pass


class CalibrationError(DomainError):
    pass
