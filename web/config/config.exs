import Config

config :pdf_control_web, PdfControlWeb.Endpoint,
  url: [host: "localhost"],
  adapter: Bandit.PhoenixAdapter,
  render_errors: [formats: [html: PdfControlWeb.ErrorHTML], layout: false],
  pubsub_server: PdfControl.PubSub,
  live_view: [signing_salt: "pdf-control-live"],
  secret_key_base: String.duplicate("local-development-only-", 4)

config :phoenix, :json_library, Jason
config :logger, level: :info
import_config "#{config_env()}.exs"
