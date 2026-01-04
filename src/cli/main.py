"""Main CLI interface for PokeBuy"""

import sys
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..api import EbayClient
from ..services import CacheService, PriceAnalyzer, DealFinder
from ..config import EBAY_APP_ID, DEFAULT_DISCOUNT_THRESHOLD


console = Console()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    PokeBuy - Pokemon Card Deal Finder

    Find Pokemon cards listed at less than their market value on eBay.
    """
    pass


@cli.command()
@click.argument('search_query')
@click.option(
    '--discount',
    '-d',
    type=float,
    default=DEFAULT_DISCOUNT_THRESHOLD,
    help='Minimum discount percentage (default: 50%)'
)
@click.option(
    '--max-results',
    '-n',
    type=int,
    default=20,
    help='Maximum number of results to show (default: 20)'
)
@click.option(
    '--min-price',
    type=float,
    default=None,
    help='Minimum price filter'
)
@click.option(
    '--max-price',
    type=float,
    default=None,
    help='Maximum price filter'
)
@click.option(
    '--listing-type',
    type=click.Choice(['Auction', 'FixedPrice'], case_sensitive=False),
    default=None,
    help='Filter by listing type'
)
@click.option(
    '--no-cache',
    is_flag=True,
    help='Skip cache and fetch fresh market data'
)
@click.option(
    '--export',
    type=click.Path(),
    default=None,
    help='Export results to CSV file'
)
def search(search_query, discount, max_results, min_price, max_price, listing_type, no_cache, export):
    """
    Search for Pokemon card deals on eBay.

    Examples:

      pokebuy search "Charizard PSA 10"

      pokebuy search "Pikachu" --discount 60 --max-results 10

      pokebuy search "Mewtwo Base Set" --listing-type Auction
    """
    # Check if eBay API key is configured
    if not EBAY_APP_ID:
        console.print(Panel(
            "[red]eBay API Key not configured![/red]\n\n"
            "Please set EBAY_APP_ID in your .env file.\n"
            "Get your API key at: https://developer.ebay.com/",
            title="Configuration Error",
            border_style="red"
        ))
        sys.exit(1)

    # Initialize services
    try:
        ebay = EbayClient()
        cache = CacheService()
        price_analyzer = PriceAnalyzer(ebay, cache)
        deal_finder = DealFinder(ebay, price_analyzer, cache)
    except Exception as e:
        console.print(f"[red]Error initializing services: {e}[/red]")
        sys.exit(1)

    # Show search header
    console.print()
    console.print(Panel(
        f"[bold cyan]Searching for:[/bold cyan] {search_query}\n"
        f"[bold cyan]Discount threshold:[/bold cyan] {discount}%",
        title="🔍 PokeBuy Search",
        border_style="cyan"
    ))
    console.print()

    # Search for deals with progress indicator
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task1 = progress.add_task("[cyan]Fetching sold listings to calculate market value...", total=None)
        task2 = progress.add_task("[cyan]Searching active listings...", total=None)
        task3 = progress.add_task("[cyan]Analyzing deals...", total=None)

        try:
            deals = deal_finder.find_deals(
                search_query=search_query,
                discount_threshold=discount,
                max_results=max_results,
                min_price=min_price,
                max_price=max_price,
                listing_type=listing_type
            )
        except Exception as e:
            console.print(f"[red]Error searching for deals: {e}[/red]")
            sys.exit(1)

    # Display results
    if not deals:
        console.print("[yellow]No listings found matching your criteria.[/yellow]")
        console.print("\nTry:")
        console.print("  - Broadening your search query")
        console.print("  - Checking if there are enough sold listings for this card")
        return

    deals_meeting_threshold = len([d for d in deals if d.discount_percent >= discount])
    console.print(f"\n[bold green]Found {len(deals)} listings ({deals_meeting_threshold} meet {discount}% threshold)![/bold green]\n")

    # Create results table
    table = Table(show_header=True, header_style="bold magenta", show_lines=True)
    table.add_column("", width=3)
    table.add_column("Card", min_width=40)
    table.add_column("Market", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Save", justify="right")
    table.add_column("Discount", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Type", justify="center")

    for deal in deals:
        # Determine row style based on whether it meets the threshold
        meets_threshold = deal.discount_percent >= discount
        if meets_threshold and deal.discount_percent >= 60:
            style = "bold red"
            row_style = "on dark_red"
        elif meets_threshold and deal.discount_percent >= 50:
            style = "bold yellow"
            row_style = "on dark_goldenrod"
        elif meets_threshold:
            style = "bold green"
            row_style = "on dark_green"
        else:
            style = "dim white"
            row_style = None

        # Format card name (truncate if too long)
        card_name = deal.listing.title
        if len(card_name) > 45:
            card_name = card_name[:42] + "..."

        # Listing type emoji
        type_emoji = "🔨" if deal.listing.is_auction() else "💰"

        # Show emoji only for deals meeting threshold
        emoji = deal.get_emoji() if meets_threshold else ""
        
        table.add_row(
            emoji,
            f"[link={deal.listing.url}]{card_name}[/link]",
            f"[green]${deal.market_value:.2f}[/green]",
            f"[cyan]${deal.listing_price:.2f}[/cyan]",
            f"[bold green]${deal.discount_amount:.2f}[/bold green]" if deal.discount_amount > 0 else f"[red]-${abs(deal.discount_amount):.2f}[/red]",
            f"[{style}]{deal.discount_percent:.1f}%[/{style}]",
            f"[yellow]{deal.deal_score:.0f}[/yellow]",
            type_emoji,
            style=row_style
        )

    console.print(table)

    # Show legend
    console.print("\n[bold]Legend:[/bold]")
    console.print(f"  [on dark_red] 🔥 Hot Deal (>60% off) [/on dark_red]  [on dark_goldenrod] ⭐ Star Deal (50-60% off) [/on dark_goldenrod]  [on dark_green] 💎 Meets Threshold [/on dark_green]")
    console.print("  🔨 Auction  |  💰 Buy It Now")
    console.print(f"  Highlighted rows meet the {discount}% discount threshold")

    # Export to CSV if requested
    if export:
        export_to_csv(deals, export)
        console.print(f"\n[green]Results exported to {export}[/green]")


@cli.command()
@click.argument('search_query')
def trend(search_query):
    """
    Show price trend analysis for a Pokemon card.

    Example:

      pokebuy trend "Charizard Base Set PSA 10"
    """
    if not EBAY_APP_ID:
        console.print("[red]eBay API Key not configured! Set EBAY_APP_ID in .env[/red]")
        sys.exit(1)

    # Initialize services
    ebay = EbayClient()
    cache = CacheService()
    price_analyzer = PriceAnalyzer(ebay, cache)

    console.print()
    console.print(Panel(
        f"[bold cyan]Analyzing price trend for:[/bold cyan] {search_query}",
        title="📈 Price Trend Analysis",
        border_style="cyan"
    ))
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        progress.add_task("[cyan]Fetching historical sales data...", total=None)
        trend_data = price_analyzer.get_price_trend(search_query, days=90)

    if trend_data["sample_size"] == 0:
        console.print("[yellow]No sold listings found for this card.[/yellow]")
        return

    # Display trend information
    trend_emoji = {
        "rising": "📈",
        "falling": "📉",
        "stable": "➡️",
        "unknown": "❓"
    }

    console.print(f"[bold]Sample Size:[/bold] {trend_data['sample_size']} sold listings (last 90 days)")
    console.print(f"[bold]Average Price:[/bold] ${trend_data['average_price']:.2f}")
    console.print(f"[bold]Price Range:[/bold] ${trend_data['min_price']:.2f} - ${trend_data['max_price']:.2f}")
    console.print(f"[bold]Trend:[/bold] {trend_emoji[trend_data['trend']]} {trend_data['trend'].upper()}")
    console.print()


@cli.command()
def config():
    """Show current configuration."""
    from ..config import (
        EBAY_APP_ID,
        DEFAULT_DISCOUNT_THRESHOLD,
        CACHE_EXPIRY_HOURS,
        MAX_RESULTS,
        CACHE_DB_PATH
    )

    console.print()
    console.print(Panel(
        "[bold cyan]PokeBuy Configuration[/bold cyan]",
        border_style="cyan"
    ))
    console.print()

    # Configuration table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("eBay App ID", "✓ Configured" if EBAY_APP_ID else "❌ Not set")
    table.add_row("Default Discount Threshold", f"{DEFAULT_DISCOUNT_THRESHOLD}%")
    table.add_row("Cache Expiry", f"{CACHE_EXPIRY_HOURS} hours")
    table.add_row("Max Results", str(MAX_RESULTS))
    table.add_row("Cache Database", str(CACHE_DB_PATH))

    console.print(table)
    console.print()

    if not EBAY_APP_ID:
        console.print("[yellow]⚠ eBay App ID not configured. Get one at: https://developer.ebay.com/[/yellow]")
        console.print()


@cli.command()
@click.option('--all', 'clear_all', is_flag=True, help='Clear all cache entries')
@click.option('--expired', is_flag=True, help='Clear only expired entries')
def cache_clear(clear_all, expired):
    """Clear the market price cache."""
    cache = CacheService()

    if clear_all:
        cache.clear_all()
        console.print("[green]All cache entries cleared.[/green]")
    elif expired:
        count = cache.clear_expired()
        console.print(f"[green]Cleared {count} expired cache entries.[/green]")
    else:
        console.print("[yellow]Please specify --all or --expired[/yellow]")


def export_to_csv(deals, filename):
    """Export deals to CSV file"""
    import csv

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Card Name',
            'Market Value',
            'Listing Price',
            'Savings',
            'Discount %',
            'Deal Score',
            'Listing Type',
            'URL',
            'Seller',
            'Seller Feedback'
        ])

        for deal in deals:
            writer.writerow([
                deal.listing.title,
                f"${deal.market_value:.2f}",
                f"${deal.listing_price:.2f}",
                f"${deal.discount_amount:.2f}",
                f"{deal.discount_percent:.1f}%",
                f"{deal.deal_score:.0f}",
                deal.listing.listing_type,
                deal.listing.url,
                deal.listing.seller_name or "N/A",
                f"{deal.listing.seller_feedback_percent:.1f}%" if deal.listing.seller_feedback_percent else "N/A"
            ])


if __name__ == "__main__":
    cli()
