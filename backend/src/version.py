"""Application identity used to build outgoing ``User-Agent`` headers.

Every provider request should identify the app: MusicBrainz and Discogs both
require a descriptive ``User-Agent``, and it is generally good manners for the
Deezer / iTunes / Cover Art Archive calls too (PLAN §6). Providers may append a
contact address (MusicBrainz asks for one) but the base string lives here so
all outbound traffic advertises the same thing.
"""

APP_NAME = "vynl"
APP_VERSION = "0.1.0"
REPO_URL = "https://github.com/tylern4/vynl"

# Canonical User-Agent, e.g. ``vynl/0.1.0 (+https://github.com/tylern4/vynl)``.
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+{REPO_URL})"
