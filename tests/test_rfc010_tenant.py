import pytest
from uuid import UUID
from sqlalchemy import Column, String, event, select
from sqlalchemy.orm import Session, declarative_base

from packages.database.tenant import clear_tenant, set_tenant, with_tenant_rls
from packages.shared.identifiers import generate_id

Base = declarative_base()


class MockTenantModel(Base):
    __tablename__ = "mock_tenant_models"
    id = Column(String, primary_key=True)
    organization_id = Column(String, nullable=False)
    data = Column(String)


@pytest.fixture
def memory_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Attach RLS event
    event.listen(session, "do_orm_execute", with_tenant_rls)

    yield session
    session.close()


def test_tenant_isolation(memory_session):
    org_1 = UUID(str(generate_id()))
    org_2 = UUID(str(generate_id()))

    # Bypass RLS to setup test data (simulating system context)
    clear_tenant()  # Ensure no tenant is set, but wait, our hook raises if None!
    # Let's temporarily remove the hook or just use direct inserts for setup.
    # We'll use a clean session without the hook for setup.

    setup_session = Session(bind=memory_session.get_bind())
    m1 = MockTenantModel(id=str(generate_id()), organization_id=str(org_1), data="secret1")
    m2 = MockTenantModel(id=str(generate_id()), organization_id=str(org_2), data="secret2")
    setup_session.add_all([m1, m2])
    setup_session.commit()
    setup_session.close()

    # Now test with RLS Session
    # Set context to org_1
    set_tenant(org_1)

    stmt = select(MockTenantModel)
    results = memory_session.execute(stmt).scalars().all()

    assert len(results) == 1
    assert results[0].organization_id == str(org_1)
    assert results[0].data == "secret1"

    # Cross tenant access attempt
    set_tenant(org_2)
    results_2 = memory_session.execute(stmt).scalars().all()
    assert len(results_2) == 1
    assert results_2[0].data == "secret2"

    # Attempt without tenant context raises error
    clear_tenant()
    with pytest.raises(PermissionError):
        memory_session.execute(stmt).scalars().all()
