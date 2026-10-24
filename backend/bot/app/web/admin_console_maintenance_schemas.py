"""UC-08 / UA-20: a safe, optional external maintenance destination."""

from bot.app.web.http_contracts import HttpResponseModel


class ConsoleMaintenanceOut(HttpResponseModel):
    destination: str | None
