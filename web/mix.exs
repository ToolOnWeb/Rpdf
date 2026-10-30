defmodule PdfControl.MixProject do
  use Mix.Project

  def project do
    [
      app: :pdf_control_web,
      version: "1.2.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      aliases: [check: ["format --check-formatted", "compile --warnings-as-errors", "test"]]
    ]
  end

  def cli, do: [preferred_envs: [check: :test]]

  def application do
    [mod: {PdfControl.Application, []}, extra_applications: [:logger, :crypto]]
  end

  defp deps do
    [
      {:phoenix, "~> 1.8.16"},
      {:phoenix_live_view, "~> 1.2.13"},
      {:phoenix_html, "~> 4.3"},
      {:bandit, "~> 1.8"},
      {:jason, "~> 1.4"},
      {:lazy_html, ">= 0.1.0", only: :test}
    ]
  end
end
