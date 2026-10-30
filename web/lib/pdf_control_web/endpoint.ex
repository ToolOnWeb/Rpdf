defmodule PdfControlWeb.Endpoint do
  use Phoenix.Endpoint, otp_app: :pdf_control_web

  @session_options [
    store: :cookie,
    key: "_pdf_control_session",
    signing_salt: "pdf-control-session",
    same_site: "Lax",
    http_only: true
  ]
  socket("/live", Phoenix.LiveView.Socket,
    websocket: [connect_info: [session: @session_options]],
    longpoll: false
  )

  plug(Plug.Static, at: "/vendor/phoenix", from: {:phoenix, "priv/static"}, gzip: false)

  plug(Plug.Static,
    at: "/vendor/liveview",
    from: {:phoenix_live_view, "priv/static"},
    gzip: false
  )

  plug(Plug.RewriteOn, [:x_forwarded_proto])
  plug(Plug.RequestId)
  plug(Plug.Telemetry, event_prefix: [:phoenix, :endpoint])
  plug(Plug.MethodOverride)
  plug(Plug.Head)
  plug(Plug.Session, @session_options)
  plug(PdfControlWeb.Release)
end
