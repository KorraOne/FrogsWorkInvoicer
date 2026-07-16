/** Pass-through Worker: serve marketing static assets only. */
export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
