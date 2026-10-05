"""Video endpoints. Routes call app/repositories/videos.py directly."""

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import AppliedFiltersDep, DbConnection
from app.core.errors import NotFoundError
from app.repositories import videos
from app.schemas.common import ERROR_RESPONSES, LATEST_SNAPSHOT_NOTE, AppliedFilters, DataResponse, ErrorResponse, \
    FilteredResponse
from app.schemas.videos import HistoryPoint, VideoDetail, VideoPage

router = APIRouter(prefix="/videos", tags=["videos"], responses=ERROR_RESPONSES)

VideoSort = Enum("VideoSort", {k: k for k in videos.VIDEO_SORTS}, type=str)
SortOrder = Enum("SortOrder", {k: k for k in videos.SORT_ORDERS}, type=str)
VideoId = Annotated[str, Path(min_length=1, max_length=videos.VIDEO_ID_MAX)]
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Unknown video_id."}}


@router.get("", response_model=FilteredResponse[VideoPage], summary="Paginated list of trending videos",
            description=LATEST_SNAPSHOT_NOTE + " Ordering is deterministic: NULLs last, ties broken by video_id.")
def list_videos(conn: DbConnection, filters: AppliedFiltersDep,
                sort: Annotated[VideoSort, Query()] = VideoSort("views"),
                order: Annotated[SortOrder, Query()] = SortOrder("desc"),
                page: Annotated[int, Query(ge=1, le=videos.MAX_PAGE)] = 1,
                page_size: Annotated[int, Query(ge=1, le=videos.MAX_PAGE_SIZE)] = videos.DEFAULT_PAGE_SIZE,
                search: Annotated[str | None, Query(
                    description="Case-insensitive substring of the title or channel title, or an exact "
                                "video_id; 2-100 characters; wildcards are matched literally.")] = None):
    return {"filters": AppliedFilters.from_filters(filters),
            "data": videos.list_videos(conn, filters, sort=sort.value, order=order.value,
                                       page=page, page_size=page_size, search=search)}


@router.get("/{video_id}", response_model=DataResponse[VideoDetail], responses=NOT_FOUND,
            summary="Video detail (globally latest snapshot; not filtered)")
def video_detail(conn: DbConnection, video_id: VideoId):
    video = videos.get_video(conn, video_id)
    if video is None:
        raise NotFoundError("Video not found.")
    return {"data": video}


@router.get("/{video_id}/history", response_model=DataResponse[list[HistoryPoint]], responses=NOT_FOUND,
            summary="Full trending history (all countries and dates; not filtered)")
def video_history(conn: DbConnection, video_id: VideoId):
    history = videos.get_video_history(conn, video_id)
    # Existence is checked only when the history is empty: unknown -> 404, known -> [].
    if not history and videos.get_video(conn, video_id) is None:
        raise NotFoundError("Video not found.")
    return {"data": history}
