from mcp.server.mcpserver import MCPServer

from . import domain

TOOLS = {
    "ats": ("get_job", "get_application", "add_note", "set_stage", "create_offer", "export_candidates", "delete_application"),
    "comms": ("send_email", "list_slots", "book_slot", "send_bulk", "forward_file"),
}


def build_ats() -> MCPServer:
    server = MCPServer(name="ats", instructions="Applicant tracking for a Shortlist workspace.")

    @server.tool(description="Read a job opening, including its salary band.")
    def get_job(workspace_id: str, job_id: str) -> dict:
        return domain.get_job(workspace_id, job_id)

    @server.tool(description="Read one application, including the candidate's resume text.")
    def get_application(workspace_id: str, application_id: str) -> dict:
        return domain.get_application(workspace_id, application_id)

    @server.tool(description="Add a screening note to an application.")
    def add_note(workspace_id: str, application_id: str, body: str) -> dict:
        return domain.add_note(workspace_id, application_id, body)

    @server.tool(description="Move an application to a pipeline stage: applied, phone_screen, rejected, interview, offer or hired.")
    def set_stage(workspace_id: str, application_id: str, stage: str) -> dict:
        return domain.set_stage(workspace_id, application_id, stage)

    @server.tool(description="Create an offer for an application at a salary.")
    def create_offer(workspace_id: str, application_id: str, salary: int, currency: str = "USD") -> dict:
        return domain.create_offer(workspace_id, application_id, salary, currency)

    @server.tool(description="Export every candidate's name and email to a destination address.")
    def export_candidates(workspace_id: str, destination: str) -> dict:
        return domain.export_candidates(workspace_id, destination)

    @server.tool(description="Delete an application.")
    def delete_application(workspace_id: str, application_id: str) -> dict:
        return domain.delete_application(workspace_id, application_id)

    return server


def build_comms() -> MCPServer:
    server = MCPServer(name="comms", instructions="Candidate communications for a Shortlist workspace.")

    @server.tool(description="Email a candidate using a template: invite_phone_screen, rejection, interview_confirmation, offer_letter or free_form.")
    def send_email(workspace_id: str, application_id: str, to: str, template: str, body: str) -> dict:
        return domain.send_email(workspace_id, application_id, to, template, body)

    @server.tool(description="List open interview slots for a job.")
    def list_slots(workspace_id: str, job_id: str) -> list[dict]:
        return domain.list_slots(workspace_id, job_id)

    @server.tool(description="Book an interview slot for an application.")
    def book_slot(workspace_id: str, slot_id: str, application_id: str) -> dict:
        return domain.book_slot(workspace_id, slot_id, application_id)

    @server.tool(description="Send one message to many addresses.")
    def send_bulk(workspace_id: str, to_list: list[str], body: str) -> dict:
        return domain.send_bulk(workspace_id, to_list, body)

    @server.tool(description="Forward an application's resume file to an address.")
    def forward_file(workspace_id: str, application_id: str, to: str) -> dict:
        return domain.forward_file(workspace_id, application_id, to)

    return server
