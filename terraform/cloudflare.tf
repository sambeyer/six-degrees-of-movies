# ── Cloudflare Worker — reverse proxy to Cloud Run ────────────────────────────
# australia-southeast2 doesn't support Cloud Run domain mappings, so we use a
# Cloudflare Worker to proxy sixdegreesofmovies.com → the Cloud Run URL.
# The Worker is re-deployed on every `terraform apply`, keeping the Cloud Run
# URL in sync automatically after each image deploy.

locals {
  cloudrun_hostname = trimprefix(google_cloud_run_v2_service.app.uri, "https://")

  worker_script = <<-JS
    const UPSTREAM = "${local.cloudrun_hostname}";

    // Bot scanners probe for CMS/framework paths that don't exist here.
    // Reject them immediately — before making any outbound fetch to Cloud Run —
    // to avoid triggering expensive cold starts on Cloud Run.
    const BOT_PATH_PATTERNS = [
      // WordPress scanners
      /^\/wp-/i,
      /^\/wordpress/i,
      /^\/xmlrpc\.php/i,
      /\/wp-includes\//i,
      // Common CMS sub-paths (e.g. /cms/, /blog/, /shop/ prefixes used by WP scanners)
      /\/(cms|site|test|wp|wp1|wp2|shop|blog|news|website|sito|media|web|2018|2019|2020|2021|2022|2023|2024)\/wp-/i,
      // Credential/config harvesting
      /^\/\.env/i,
      /^\/backend\/\.env/i,
      /^\/\.git\//i,
      /^\/admin\/serverConfig\.json/i,
      // Other CMS/framework probes
      /^\/phpmyadmin/i,
      /^\/admin\//i,
    ];

    addEventListener('fetch', event => {
      event.respondWith(handleRequest(event.request));
    });

    async function handleRequest(request) {
      const url = new URL(request.url);
      for (const pattern of BOT_PATH_PATTERNS) {
        if (pattern.test(url.pathname)) {
          return new Response('Not Found', { status: 404 });
        }
      }
      url.hostname = UPSTREAM;
      url.protocol = 'https:';
      return fetch(new Request(url, request));
    }
  JS
}

resource "cloudflare_workers_script" "proxy" {
  account_id = var.cloudflare_account_id
  name       = "sixdegreesofmovies-proxy"
  content    = local.worker_script
}

resource "cloudflare_workers_route" "site" {
  zone_id     = var.cloudflare_zone_id
  pattern     = "${var.domain}/*"
  script_name = cloudflare_workers_script.proxy.name
}

# Dummy A record required for Cloudflare to proxy the domain.
# Traffic never reaches 192.0.2.1 — Cloudflare intercepts it via the Worker route.
resource "cloudflare_record" "root" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  content = "192.0.2.1"
  type    = "A"
  proxied = true
}
