import os

import pygame


# general setup
pygame.init()
WINDOW_WIDTH, WINDOW_HEIGHT = 1280, 720
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("WikiDeck")

# Background image
bg_image = pygame.image.load(os.path.join("assets/images/bg_main.png")).convert()
bg_image = pygame.transform.scale(bg_image, (WINDOW_WIDTH, WINDOW_HEIGHT))

# Card image
card_image = pygame.image.load(os.path.join("assets/images/card.png")).convert()
card_image = pygame.transform.scale(card_image, (100, 140))
card_rect = card_image.get_frect(center = (WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2))


running = True
clock = pygame.time.Clock()

while running:
    dt = clock.tick() / 1000  # Delta time in seconds.

    # event loop
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False


    # input
    left_mouse_pressed = pygame.mouse.get_pressed()[0] # Check if the left mouse button is pressed
    right_mouse_pressed = pygame.mouse.get_pressed()[2] # Check if the right mouse button is pressed
    mouse_pos = pygame.mouse.get_pos() # Get the current mouse position

    if left_mouse_pressed and card_rect.collidepoint(mouse_pos):
        card_rect.center = mouse_pos  # Move the card to the mouse position when dragging

    
    
    screen.blit(bg_image, (0, 0))
    screen.blit(card_image, card_rect)

    pygame.display.update()


pygame.quit()