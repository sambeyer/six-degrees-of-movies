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
    // Tarpit them all — hold the connection open for ~25 seconds to waste the
    // scanner's time. setTimeout is async so CPU cost is negligible.
    const BOT_TARPIT_PATTERNS = [
      /^\/wp-/i,
      /^\/wordpress/i,
      /^\/xmlrpc\.php/i,
      /\/wp-includes\//i,
      /\/(cms|site|test|wp|wp1|wp2|shop|blog|news|website|sito|media|web|2018|2019|2020|2021|2022|2023|2024)\/wp-/i,
      /^\/\.env/i,
      /^\/backend\/\.env/i,
      /^\/\.git\//i,
      /^\/admin\/serverConfig\.json/i,
      /^\/phpmyadmin/i,
      /^\/admin\//i,
    ];

    // Streams a fake response one byte every ~1.4s, holding the connection open
    // for ~25 seconds total (safely under Cloudflare's 30s wall-clock limit).
    function tarpit() {
      const payload = '<!-- Loading... -->';
      const encoder = new TextEncoder();
      let i = 0;
      const stream = new ReadableStream({
        async pull(controller) {
          if (i < payload.length) {
            await new Promise(r => setTimeout(r, 1400));
            controller.enqueue(encoder.encode(payload[i++]));
          } else {
            controller.close();
          }
        }
      });
      return new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    addEventListener('fetch', event => {
      event.respondWith(handleRequest(event.request));
    });

    async function handleRequest(request) {
      const url = new URL(request.url);
      for (const pattern of BOT_TARPIT_PATTERNS) {
        if (pattern.test(url.pathname)) return tarpit();
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
