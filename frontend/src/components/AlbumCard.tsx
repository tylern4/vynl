import { Link } from 'react-router-dom'
import { Star } from 'lucide-react'
import { CoverImage } from './CoverImage'
import type { Album } from '../types'

interface AlbumCardProps {
  album: Album
  /** When provided, renders the favorite star toggle in the corner. */
  onToggleFavorite?: (album: Album) => void
  canEdit?: boolean
}

/** Shelf grid card: lazy cover, title/artist/year, first tags, favorite star. */
export function AlbumCard({ album, onToggleFavorite, canEdit = true }: AlbumCardProps) {
  const favLabel = album.favorite
    ? `Remove ${album.title} from favorites`
    : `Add ${album.title} to favorites`

  return (
    <article className="album-card">
      <Link to={`/album/${album.id}`} className="album-card-link">
        <CoverImage
          albumId={album.id}
          coverUrl={album.cover_url}
          alt={`${album.title} cover`}
          className="album-card-cover"
        />
        <div className="album-card-body">
          <h3 className="album-card-title">{album.title}</h3>
          <p className="album-card-meta">
            {album.artist}
            {album.year ? ` · ${album.year}` : ''}
          </p>
          {album.tags.length > 0 && (
            <div className="album-card-tags">
              {album.tags.slice(0, 3).map((tag) => (
                <span key={tag} className="tag-chip tag-chip-sm">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </Link>
      {onToggleFavorite && (
        <button
          type="button"
          className={`icon-btn fav-btn${album.favorite ? ' is-fav' : ''}`}
          aria-label={favLabel}
          aria-pressed={album.favorite}
          disabled={!canEdit}
          onClick={() => onToggleFavorite(album)}
        >
          <Star size={16} fill={album.favorite ? 'currentColor' : 'none'} />
        </button>
      )}
    </article>
  )
}
