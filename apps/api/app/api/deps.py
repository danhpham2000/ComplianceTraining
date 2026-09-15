from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth import Actor, get_current_actor


DBSession = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_current_actor)]

