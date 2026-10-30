defmodule PdfControl.Application do
  use Application

  def start(_type, _args) do
    children = [
      {Phoenix.PubSub, name: PdfControl.PubSub},
      PdfControl.Metrics,
      PdfControl.Jobs,
      PdfControl.Engine,
      PdfControlWeb.Endpoint
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: PdfControl.Supervisor)
  end

  def config_change(changed, _new, removed),
    do: PdfControlWeb.Endpoint.config_change(changed, removed)
end
