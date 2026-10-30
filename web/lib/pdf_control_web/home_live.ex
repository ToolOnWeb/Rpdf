defmodule PdfControlWeb.HomeLive do
  use Phoenix.LiveView, layout: false
  @impl true
  def mount(_params, session, socket) do
    workspace = Map.fetch!(session, "workspace_id")

    if connected?(socket) do
      Phoenix.PubSub.subscribe(PdfControl.PubSub, "workspace:" <> workspace)
      PdfControl.Metrics.track(self())
    end

    {:ok,
     assign(socket,
       status: label(PdfControl.Jobs.status(workspace)),
       workspace_html: PdfControlWeb.Assets.body()
     )}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div id="pdf-live-shell">
      <aside :if={@status} id="live-job-status" role="status" aria-live="polite"
        style="padding:8px 20px;font:inherit;border-bottom:1px solid currentColor">
        {@status}
      </aside>
      <div id="pdf-workspace" phx-hook="PdfWorkspace" phx-update="ignore">
        {Phoenix.HTML.raw(@workspace_html)}
      </div>
    </div>
    """
  end

  @impl true
  def handle_info({:job, state}, socket) do
    {:noreply, assign(socket, status: label(state))}
  end

  defp label(nil), do: nil
  defp label(:queued), do: "المهمة في قائمة الانتظار / Queued"
  defp label(:running), do: "جارٍ معالجة الملف / Processing"
  defp label(:succeeded), do: "اكتملت المعالجة / Complete"
  defp label(:failed), do: "تعذّرت المعالجة / Failed"
end
