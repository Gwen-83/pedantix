/**
 * Configuration Pédantix pour l'hébergement en ligne (Netlify + Render + Supabase)
 *
 * Pour héberger sur Netlify :
 * 1. Déployez votre backend sur Render (ex: https://pedantix-api.onrender.com)
 * 2. Renseignez l'URL ci-dessous dans BACKEND_URL
 *
 * Si BACKEND_URL est vide (""), le jeu se connecte automatiquement au même domaine
 * (idéal pour le développement local ou si Render héberge l'API et les fichiers statiques).
 */
window.PEDANTIX_CONFIG = {
  // Ex: "https://pedantix-api.onrender.com"
  BACKEND_URL: ""
};
