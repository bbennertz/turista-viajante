import pytest


@pytest.fixture(autouse=True)
def _no_network_for_hotel_times(monkeypatch):
    """A linha do hotel ao vivo consultaria o OSRM público; testes não podem depender da rede.

    Falha como o serviço indisponível, o que exercita o caminho de aproximação (com aviso)."""

    def unavailable(*args, **kwargs):
        raise RuntimeError("serviço de rotas indisponível (teste)")

    monkeypatch.setattr("api.route.hotel_times", unavailable)
