defmodule PdfControlWeb.Router do
  use Phoenix.Router
  import Plug.Conn
  import Phoenix.Controller
  import Phoenix.LiveView.Router

  pipeline :browser do
    plug(:accepts, ["html"])
    plug(:fetch_session)
    plug(:protect_from_forgery)
    plug(:put_secure_browser_headers)
    plug(PdfControlWeb.Session)
    plug(:put_root_layout, html: {PdfControlWeb.Layouts, :root})
  end

  pipeline :api do
    plug(:fetch_session)
    plug(PdfControlWeb.Session)
    plug(PdfControlWeb.SameOrigin)
  end

  scope "/" do
    pipe_through(:browser)
    live("/", PdfControlWeb.HomeLive, :index)
  end

  # These source assets contain no user data. Like Plug.Static assets, they are
  # public GET resources and do not pass through form CSRF response verification.
  scope "/" do
    get("/app.css", PdfControlWeb.AssetController, :css)
    get("/workspace.js", PdfControlWeb.AssetController, :workspace)
    get("/liveview.js", PdfControlWeb.AssetController, :liveview)
  end

  scope "/api" do
    pipe_through(:api)
    match(:*, "/*path", PdfControlWeb.ApiController, :dispatch)
  end
end
