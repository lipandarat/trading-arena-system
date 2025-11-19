"""Initial migration for all models

Revision ID: ade7b84f2f6a
Revises:
Create Date: 2025-11-18 12:29:11.390443

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ade7b84f2f6a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""

    # Create agents table
    op.create_table('agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=False),
        sa.Column('llm_model', sa.String(length=255), nullable=False),
        sa.Column('llm_config', sa.Text(), nullable=True),
        sa.Column('risk_profile', sa.String(length=50), nullable=False),
        sa.Column('max_leverage', sa.Float(), nullable=True),
        sa.Column('max_drawdown', sa.Float(), nullable=True),
        sa.Column('initial_capital', sa.Float(), nullable=True),
        sa.Column('current_capital', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_agents_id'), 'agents', ['id'], unique=False)

    # Create competitions table
    op.create_table('competitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('prize_pool', sa.Float(), nullable=True),
        sa.Column('entry_fee', sa.Float(), nullable=True),
        sa.Column('max_participants', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create competition_entries table
    op.create_table('competition_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('competition_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.Column('final_rank', sa.Integer(), nullable=True),
        sa.Column('final_score', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['competition_id'], ['competitions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_competition_entries_agent_id'), 'competition_entries', ['agent_id'], unique=False)
    op.create_index(op.f('ix_competition_entries_competition_id'), 'competition_entries', ['competition_id'], unique=False)

    # Create trades table
    op.create_table('trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('competition_entry_id', sa.Integer(), nullable=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('exchange', sa.String(length=50), nullable=True),
        sa.Column('trade_group', sa.String(length=100), nullable=True),
        sa.Column('signal_action', sa.String(length=10), nullable=False),
        sa.Column('signal_reasoning', sa.Text(), nullable=True),
        sa.Column('signal_confidence', sa.Float(), nullable=True),
        sa.Column('signal_timestamp', sa.DateTime(), nullable=False),
        sa.Column('order_id', sa.String(length=100), nullable=True),
        sa.Column('order_type', sa.String(length=20), nullable=True),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('executed_quantity', sa.Float(), nullable=False),
        sa.Column('executed_price', sa.Float(), nullable=False),
        sa.Column('execution_timestamp', sa.DateTime(), nullable=False),
        sa.Column('fee', sa.Float(), nullable=True),
        sa.Column('fee_currency', sa.String(length=10), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['competition_entry_id'], ['competition_entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trades_agent_id'), 'trades', ['agent_id'], unique=False)
    op.create_index(op.f('ix_trades_id'), 'trades', ['id'], unique=False)
    op.create_index(op.f('ix_trades_symbol'), 'trades', ['symbol'], unique=False)
    op.create_index(op.f('ix_trades_order_id'), 'trades', ['order_id'], unique=False)
    op.create_index('ix_trades_trade_group', 'trades', ['trade_group'], unique=False)

    # Create positions table
    op.create_table('positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('competition_entry_id', sa.Integer(), nullable=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('exchange', sa.String(length=50), nullable=True),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('size', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('current_price', sa.Float(), nullable=True),
        sa.Column('unrealized_pnl', sa.Float(), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('total_fees', sa.Float(), nullable=True),
        sa.Column('leverage', sa.Float(), nullable=True),
        sa.Column('margin_used', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['competition_entry_id'], ['competition_entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_positions_agent_id'), 'positions', ['agent_id'], unique=False)
    op.create_index('ix_positions_symbol', 'positions', ['symbol'], unique=False)
    op.create_index('ix_positions_status', 'positions', ['status'], unique=False)

    # Create scores table
    op.create_table('scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('competition_entry_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('metric_type', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('calculation_method', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['competition_entry_id'], ['competition_entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scores_agent_id'), 'scores', ['agent_id'], unique=False)
    op.create_index('ix_scores_competition_entry', 'scores', ['competition_entry_id'], unique=False)
    op.create_index('ix_scores_timestamp', 'scores', ['timestamp'], unique=False)
    op.create_index('ix_scores_metric_name', 'scores', ['metric_name'], unique=False)

    # Create rankings table
    op.create_table('rankings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('competition_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('competition_entry_id', sa.Integer(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('total_return', sa.Float(), nullable=True),
        sa.Column('sharpe_ratio', sa.Float(), nullable=True),
        sa.Column('max_drawdown', sa.Float(), nullable=True),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['competition_id'], ['competitions.id'], ),
        sa.ForeignKeyConstraint(['competition_entry_id'], ['competition_entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rankings_competition_id'), 'rankings', ['competition_id'], unique=False)
    op.create_index(op.f('ix_rankings_agent_id'), 'rankings', ['agent_id'], unique=False)
    op.create_index('ix_rankings_rank', 'rankings', ['rank'], unique=False)
    op.create_index('ix_rankings_computed_at', 'rankings', ['calculated_at'], unique=False)

    # Create performance table
    op.create_table('performances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('competition_entry_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('starting_capital', sa.Float(), nullable=False),
        sa.Column('ending_capital', sa.Float(), nullable=False),
        sa.Column('total_return', sa.Float(), nullable=False),
        sa.Column('total_return_pct', sa.Float(), nullable=False),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('profit_factor', sa.Float(), nullable=True),
        sa.Column('sharpe_ratio', sa.Float(), nullable=True),
        sa.Column('sortino_ratio', sa.Float(), nullable=True),
        sa.Column('max_drawdown', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.Column('volatility', sa.Float(), nullable=True),
        sa.Column('var_95', sa.Float(), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('winning_trades', sa.Integer(), nullable=True),
        sa.Column('losing_trades', sa.Integer(), nullable=True),
        sa.Column('avg_win', sa.Float(), nullable=True),
        sa.Column('avg_loss', sa.Float(), nullable=True),
        sa.Column('largest_win', sa.Float(), nullable=True),
        sa.Column('largest_loss', sa.Float(), nullable=True),
        sa.Column('avg_trade_duration', sa.Float(), nullable=True),
        sa.Column('total_fees', sa.Float(), nullable=True),
        sa.Column('net_profit', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['competition_entry_id'], ['competition_entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performances_agent_id'), 'performances', ['agent_id'], unique=False)
    op.create_index('ix_performances_timestamp', 'performances', ['timestamp'], unique=False)
    op.create_index('ix_performances_period_type', 'performances', ['period_type'], unique=False)


def downgrade() -> None:
    """Downgrade database schema."""

    # Drop tables in reverse order (to handle foreign key constraints)
    op.drop_table('performances')
    op.drop_table('rankings')
    op.drop_table('scores')
    op.drop_table('positions')
    op.drop_table('trades')
    op.drop_table('competition_entries')
    op.drop_table('competitions')
    op.drop_table('agents')