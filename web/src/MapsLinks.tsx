import { googleMapsLinks } from "./maps";
import type { LatLng, Mode, Stop } from "./types";

interface Props {
  hotel: LatLng;
  stops: Stop[];
  mode: Mode;
  className?: string;
}

/** Botão(ões) que abrem a rota no Google Maps; uma lista longa vira "Parte 1", "Parte 2"… */
export function MapsLinks({ hotel, stops, mode, className = "secondary" }: Props) {
  const links = googleMapsLinks(hotel, stops, mode);
  if (links.length === 0) return null;
  return (
    <>
      {links.map((href, i) => (
        <a
          key={href}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className={`btn ${className}`}
          title="Abre o Google Maps com a rota na ordem do roteiro"
        >
          {links.length === 1 ? "Abrir no Google Maps" : `Google Maps · parte ${i + 1} de ${links.length}`}
        </a>
      ))}
    </>
  );
}
