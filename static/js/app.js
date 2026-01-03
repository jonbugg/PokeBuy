// PokeBuy Web App JavaScript

function toggleFilters() {
    const filters = document.getElementById('advancedFilters');
    filters.style.display = filters.style.display === 'none' ? 'block' : 'none';
}

function quickSearch(query) {
    document.getElementById('searchQuery').value = query;
    searchDeals();
}

async function searchDeals() {
    const query = document.getElementById('searchQuery').value.trim();

    if (!query) {
        showError('Please enter a search query');
        return;
    }

    // Get filter values
    const discount = document.getElementById('discount').value;
    const maxResults = document.getElementById('maxResults').value;
    const minPrice = document.getElementById('minPrice').value;
    const maxPrice = document.getElementById('maxPrice').value;
    const listingType = document.getElementById('listingType').value;

    // Show loading, hide results and errors
    document.getElementById('loading').style.display = 'block';
    document.getElementById('error').style.display = 'none';
    document.getElementById('resultsSummary').style.display = 'none';
    document.getElementById('dealsContainer').innerHTML = '';

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query,
                discount,
                max_results: maxResults,
                min_price: minPrice || null,
                max_price: maxPrice || null,
                listing_type: listingType || null
            })
        });

        const data = await response.json();

        // Hide loading
        document.getElementById('loading').style.display = 'none';

        if (!response.ok) {
            showError(data.error || 'An error occurred');
            return;
        }

        if (!data.success) {
            showError(data.error || 'Search failed');
            return;
        }

        // Show results
        displayResults(data);

    } catch (error) {
        document.getElementById('loading').style.display = 'none';
        showError('Network error. Please check your connection and try again.');
        console.error(error);
    }
}

function displayResults(data) {
    const container = document.getElementById('dealsContainer');
    const summary = document.getElementById('resultsSummary');

    if (data.deals.length === 0) {
        summary.style.display = 'block';
        summary.innerHTML = `
            <p style="color: #856404;">No deals found for "${data.query}"</p>
            <p style="font-size: 0.9rem; font-weight: normal; margin-top: 10px;">
                Try lowering the discount threshold or using broader search terms.
            </p>
        `;
        return;
    }

    // Show summary
    summary.style.display = 'block';
    summary.innerHTML = `
        <p>Found <strong>${data.count}</strong> deals for "${data.query}"</p>
        <p style="font-size: 0.9rem; font-weight: normal; margin-top: 5px;">
            ${data.discount_threshold}% or more off market value
        </p>
    `;

    // Display deals
    data.deals.forEach(deal => {
        const dealCard = createDealCard(deal);
        container.appendChild(dealCard);
    });
}

function createDealCard(deal) {
    const card = document.createElement('div');
    card.className = 'deal-card';

    if (deal.is_hot_deal) {
        card.classList.add('hot');
    } else if (deal.is_star_deal) {
        card.classList.add('star');
    } else if (deal.discount_percent >= 40) {
        card.classList.add('good');
    }

    const imageUrl = deal.image_url || 'https://via.placeholder.com/300x200?text=No+Image';
    const listingTypeEmoji = deal.listing_type === 'Auction' ? '🔨' : '💰';
    const listingTypeText = deal.listing_type === 'Auction' ? 'Auction' : 'Buy It Now';

    card.innerHTML = `
        ${deal.image_url ? `<img src="${imageUrl}" alt="${deal.card_name}" class="deal-image">` : ''}
        <div class="deal-content">
            <div class="deal-emoji">${deal.emoji}</div>
            <h3 class="deal-title">${truncate(deal.card_name, 80)}</h3>

            <div class="deal-prices">
                <div>
                    <div style="font-size: 0.8rem; color: #666;">Market</div>
                    <div class="market-value">$${deal.market_value.toFixed(2)}</div>
                </div>
                <div>
                    <div style="font-size: 0.8rem; color: #666;">Price</div>
                    <div class="listing-price">$${deal.listing_price.toFixed(2)}</div>
                </div>
            </div>

            <div class="deal-stats">
                <div class="stat">
                    <div class="stat-label">Save</div>
                    <div class="stat-value discount">$${deal.discount_amount.toFixed(2)}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Discount</div>
                    <div class="stat-value discount">${deal.discount_percent.toFixed(1)}%</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Score</div>
                    <div class="stat-value score">${deal.deal_score.toFixed(0)}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Type</div>
                    <div class="stat-value">${listingTypeEmoji}</div>
                </div>
            </div>

            <div class="deal-meta">
                ${deal.condition ? `<span>📦 ${deal.condition}</span>` : ''}
                ${deal.seller_feedback_percent ? `<span>⭐ ${deal.seller_feedback_percent.toFixed(1)}%</span>` : ''}
                ${deal.free_shipping ? `<span>🚚 Free Shipping</span>` : ''}
            </div>

            <a href="${deal.url}" target="_blank" class="deal-link">
                View on eBay →
            </a>
        </div>
    `;

    return card;
}

function truncate(str, maxLength) {
    if (str.length <= maxLength) return str;
    return str.substring(0, maxLength - 3) + '...';
}

function showError(message) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

// Allow Enter key to search
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('searchQuery').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            searchDeals();
        }
    });
});
