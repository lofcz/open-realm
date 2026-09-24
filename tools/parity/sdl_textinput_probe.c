#include <SDL2/SDL.h>
int main(void) {
    SDL_Event event = { .text = { .type = SDL_TEXTINPUT, .text = "test" } };
    if (SDL_InitSubSystem(SDL_INIT_EVENTS)) return 2;
    int result = SDL_PushEvent(&event);
    SDL_QuitSubSystem(SDL_INIT_EVENTS);
    return result == 1 ? 0 : 1;
}
