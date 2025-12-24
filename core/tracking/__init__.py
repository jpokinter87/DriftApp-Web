"""Module de gestion du suivi de coupole."""


def __getattr__(name):
    """
    Import lazy pour éviter l'import d'astropy au chargement du module.
    Permet aux tests d'importer adaptive_tracking sans avoir astropy.
    """
    if name == 'TrackingSession':
        from core.tracking.tracker import TrackingSession
        return TrackingSession
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ['TrackingSession']