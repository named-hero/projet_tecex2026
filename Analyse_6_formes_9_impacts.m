clear; clc; close all

formes_a_analyser = 3;  % Analyse tous les fichiers deja simules.
% Colonnes : Rx moy/min/max, Ry moy/min/max, C moy/min/max, autre max.
resumes = NaN(6,10);
noms = {'Cercle','Rectangle','Trapeze trou et deux coupes', ...
        'Palette de peintre','Forme en D','Contour de piano'};

for forme = formes_a_analyser % Analyse toutes les formes. Pas vraiment un choix
    nom_fichier = sprintf('Sim_9_impacts_forme_%d.mat',forme);
    if ~isfile(nom_fichier)
        fprintf('Forme %d : fichier absent, analyse ignoree.\n',forme)
        continue
    end
    S = load(nom_fichier);
    assert(isfield(S,'positions_sondes') && isfield(S,'indices_impacts') ...
        && size(S.impacts,1)==9 && size(S.sensor_data,1)==size(S.positions_sondes,1), ...
        'Fichier incompatible : relancer Simulation_6_formes_9_impacts.m')
    signaux = double(S.sensor_data);
    energies = sqrt(sum(signaux.^2,2));
    if any(energies <= 0)
        error('Forme %d : au moins un signal est nul.',forme)
    end
    norm_signaux = signaux ./ energies;
    I = S.impacts(:,1); % Prennds la liste des impacts
    J = S.impacts(:,2);
    res_x = NaN(9,1); % Erreur si plus que 9 points
    res_y = NaN(9,1); % Erreur si plus que 9 points
    contraste = NaN(9,1); % Erreur si plus que 9 points
    confusion_max = NaN(9,1); % Erreur si plus que 9 points
    couleurs = zeros(9,9); % Erreur si plus que 9 points

    figure('Name',[noms{forme} ' - profils'],'Color','w', ...
        'Position',[80 80 1500 1050]); % Pas sûr ce que fait Position - Olivier
    disposition_profils = tiledlayout(3,3,'TileSpacing','loose','Padding','loose');
    for p = 1:9 % Dépend encore une fois d'un nombre d'impact - Olivier
        ref = S.indices_impacts(p);
        % Meme definition que les anciens codes : maximum de la
        % correlation croisee normalisee, sur tous les decalages temporels.
        coeff = zeros(size(signaux,1),1);
        for q = 1:size(signaux,1)
            c = xcorr(norm_signaux(ref,:),norm_signaux(q,:));
            coeff(q) = max(abs(c));
        end
        couleurs(p,:) = coeff(S.indices_impacts); %N'est pas à jour selon nouvelles méthode
        autres = 1:9;
        autres(p) = [];
        contraste(p) = 1/mean(couleurs(p,autres));
        confusion_max(p) = max(couleurs(p,autres));

        etendue_profil = 6;
        if forme == 1 && (p == 4 || p == 6)
            etendue_profil = 10;  % Correspond aux nouvelles sondes du cercle.
        end
        masque_x = S.positions_sondes(:,2)==J(p) ...
            & abs(S.positions_sondes(:,1)-I(p))<=etendue_profil;
        masque_y = S.positions_sondes(:,1)==I(p) ...
            & abs(S.positions_sondes(:,2)-J(p))<=etendue_profil;
        [absc_x,ordre_x] = sort((S.positions_sondes(masque_x,1)-I(p))*S.dx*100);
        [absc_y,ordre_y] = sort((S.positions_sondes(masque_y,2)-J(p))*S.dy*100);
        courbe_x = coeff(masque_x); courbe_x = courbe_x(ordre_x);
        courbe_y = coeff(masque_y); courbe_y = courbe_y(ordre_y);
        res_x(p) = largeur_mi_hauteur(absc_x,courbe_x);
        res_y(p) = largeur_mi_hauteur(absc_y,courbe_y);
        ax = nexttile(disposition_profils);
        plot(ax,absc_x,courbe_x,'-','LineWidth',2,'Color',[0.10 0.35 0.70]);hold(ax,'on')
        plot(ax,absc_y,courbe_y,'-','LineWidth',2,'Color',[0.85 0.35 0.10])
        yline(ax,0.5,'--','Color',[0.4 0.4 0.4]);
        xline(ax,0,':','Color',[0.5 0.5 0.5]);grid(ax,'on')
        if p>=7, xlabel(ax,'Deplacement [cm]'); end
        if mod(p-1,3)==0, ylabel(ax,'Correlation maximale'); end
        title(sprintf('Impact %d | Rx %.2f cm | Ry %.2f cm',p,res_x(p),res_y(p)))
        xlim([-etendue_profil*S.dx*100 etendue_profil*S.dx*100]);ylim([0 1.05])
    end
    title(disposition_profils,{[noms{forme} ' : profils locaux de correlation'], ...
        'Bleu : direction x   |   Orange : direction y   |   Tirets : mi-hauteur (0,5)   |   Pointilles : impact de reference'})

    figure('Name',[noms{forme} ' - grille'],'Color','w', ...
        'Position',[100 100 1500 1050]);
    disposition_carte = tiledlayout(3,3,'TileSpacing','loose','Padding','loose');
    % Une echelle commune met en evidence les differences entre les autres
    % impacts. Le point de reference est exclu : sa correlation vaut 1.
    echelle_max = min(1,max(0.1,ceil(10*max(confusion_max))/10));
    y_cm = S.impacts(:,2)*S.dy*100;
    x_cm = S.impacts(:,1)*S.dx*100;
    marge_y = max(1,0.15*(max(y_cm)-min(y_cm)));
    marge_x = max(1,0.15*(max(x_cm)-min(x_cm)));
    for p=1:9
        ax = nexttile(disposition_carte);
        autres = setdiff(1:9,p);
        scatter(ax,y_cm(autres),x_cm(autres),115,couleurs(p,autres), ...
            'filled','MarkerEdgeColor','w','LineWidth',0.8);
        hold(ax,'on')
        plot(ax,y_cm(p),x_cm(p),'o','MarkerSize',12, ...
            'MarkerFaceColor','w','MarkerEdgeColor','k','LineWidth',2)
        grid(ax,'on'); axis(ax,'equal')
        xlim(ax,[min(y_cm)-marge_y max(y_cm)+marge_y])
        ylim(ax,[min(x_cm)-marge_x max(x_cm)+marge_x])
        set(ax,'YDir','reverse')
        caxis(ax,[0 echelle_max])
        if p>=7, xlabel(ax,'Position y [cm]'); end
        if mod(p-1,3)==0, ylabel(ax,'Position x [cm]'); end
        title(ax,sprintf('Impact %d  |  autre max : %.2f',p,confusion_max(p)))
    end
    colormap(gcf,parula(256))
    % L'echelle occupe sa propre zone sous les neuf cartes.
    barre = colorbar(ax,'southoutside');
    barre.Layout.Tile = 'south';
    barre.Label.String = 'Ressemblance avec la reference (0 = faible, 1 = identique)';
    title(disposition_carte,{[noms{forme} ' : ressemblance entre les 9 impacts'], ...
        'Cercle blanc : reference   |   Cercles colores : huit autres impacts   |   Meme echelle pour les neuf cartes'})

    fprintf('\n%s\n',noms{forme})
    fprintf('Impact | R x [cm] | R y [cm] | Contraste grille | Autre max\n')
    for p=1:9
        fprintf('%6d | %8.2f | %8.2f | %14.2f | %9.2f\n', ...
            p,res_x(p),res_y(p),contraste(p),confusion_max(p))
    end
    [contraste_min,impact_c_min] = min(contraste);
    [contraste_max,impact_c_max] = max(contraste);
    fprintf('Contraste moyen de grille : %.2f\n',mean(contraste))
    fprintf('Contraste le plus faible : %.2f (impact %d)\n',contraste_min,impact_c_min)
    fprintf('Contraste le plus eleve : %.2f (impact %d)\n',contraste_max,impact_c_max)
    resumes(forme,7:10) = [mean(contraste),contraste_min, ...
        contraste_max,max(confusion_max)];
    if any(isnan(res_x))
        fprintf('Rx indetermine pour les impacts : ')
        fprintf('%d ',find(isnan(res_x)))
        fprintf('\n')
    else
        [rx_min,impact_rx_min] = min(res_x);
        [rx_max,impact_rx_max] = max(res_x);
        resumes(forme,1:3) = [mean(res_x),rx_min,rx_max];
        fprintf('Rx moyen : %.2f cm | meilleur : %.2f (impact %d) | pire : %.2f (impact %d)\n', ...
            mean(res_x),rx_min,impact_rx_min,rx_max,impact_rx_max)
    end
    if any(isnan(res_y))
        fprintf('Ry indetermine pour les impacts : ')
        fprintf('%d ',find(isnan(res_y)))
        fprintf('\n')
    else
        [ry_min,impact_ry_min] = min(res_y);
        [ry_max,impact_ry_max] = max(res_y);
        resumes(forme,4:6) = [mean(res_y),ry_min,ry_max];
        fprintf('Ry moyen : %.2f cm | meilleur : %.2f (impact %d) | pire : %.2f (impact %d)\n', ...
            mean(res_y),ry_min,impact_ry_min,ry_max,impact_ry_max)
    end
    fprintf('Pire ressemblance avec un autre impact : %.2f\n',resumes(forme,10))
end

fprintf('\nSYNTHESE DES SIX FORMES\n')
fprintf('Forme | Rx moy | Rx min | Rx max | Ry moy | Ry min | Ry max | C moy | C min | C max | autre max\n')
for forme=formes_a_analyser
    fprintf('%5d | %6.2f | %6.2f | %6.2f | %6.2f | %6.2f | %6.2f | %5.2f | %5.2f | %5.2f | %9.2f  %s\n', ...
        forme,resumes(forme,:),noms{forme})
end
fprintf('\nRx et Ry [cm] = largeurs a mi-hauteur selon chaque direction.\n')
fprintf('C = 1 / moyenne des correlations avec les huit autres impacts.\n')
fprintf('Une petite R et une petite ressemblance maximale sont souhaitables.\n')
fprintf('Cette simulation acoustique 2D ne modelise pas les ondes de flexion d''une vraie plaque.\n')

function largeur = largeur_mi_hauteur(x,c)
    largeur = NaN;
    milieu = find(abs(x)<1e-10,1);
    if isempty(milieu), return, end
    gauche = find(c(1:milieu-1)<=0.5,1,'last');
    droite_rel = find(c(milieu+1:end)<=0.5,1,'first');
    if isempty(gauche) || isempty(droite_rel), return, end
    droite = milieu + droite_rel;
    if c(gauche+1)==c(gauche) || c(droite)==c(droite-1), return, end
    xg = x(gauche)+(0.5-c(gauche))*(x(gauche+1)-x(gauche)) ...
        /(c(gauche+1)-c(gauche));
    xd = x(droite-1)+(0.5-c(droite-1))*(x(droite)-x(droite-1)) ...
        /(c(droite)-c(droite-1));
    largeur = xd-xg;
end
