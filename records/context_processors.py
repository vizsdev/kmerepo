from django.conf import settings


def project_tracker(request):
    """Expose the kaon_tracker URL to every template. Only http(s) URLs are accepted."""
    url = (getattr(settings, "PROJECT_TRACKER_URL", "") or "").strip()
    return {"project_tracker_url": url if url.lower().startswith(("http://", "https://")) else ""}
