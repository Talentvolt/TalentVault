document.addEventListener("DOMContentLoaded", function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Basic drag and drop for Kanban (visual only for template)
    const kanbanCards = document.querySelectorAll('.kanban-card');
    const kanbanColumns = document.querySelectorAll('.kanban-body');

    kanbanCards.forEach(card => {
        card.setAttribute('draggable', true);
        card.addEventListener('dragstart', () => {
            card.classList.add('dragging');
            card.style.opacity = '0.5';
        });
        card.addEventListener('dragend', () => {
            card.classList.remove('dragging');
            card.style.opacity = '1';
        });
    });

    kanbanColumns.forEach(column => {
        column.addEventListener('dragover', e => {
            e.preventDefault();
            const draggingCard = document.querySelector('.dragging');
            if (draggingCard) {
                column.appendChild(draggingCard);
            }
        });
    });
});
