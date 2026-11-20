from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    departure_date: Mapped[str] = mapped_column(String, nullable=False)
    passengers: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    fares: Mapped[list[Fare]] = relationship(
        back_populates="search",
        cascade="all, delete-orphan",
    )


class Fare(Base):
    __tablename__ = "fares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    departure_date: Mapped[str] = mapped_column(String, nullable=False)
    cabin: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    available_seats: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[str] = mapped_column(String, nullable=False)
    booking_url: Mapped[str | None] = mapped_column(String)
    return_date: Mapped[str | None] = mapped_column(String)
    trip_type: Mapped[str] = mapped_column(String, nullable=False, default="one_way")
    price_kind: Mapped[str] = mapped_column(String, nullable=False, default="displayed")
    source_freshness: Mapped[str | None] = mapped_column(String)

    search: Mapped[Search] = relationship(back_populates="fares")
