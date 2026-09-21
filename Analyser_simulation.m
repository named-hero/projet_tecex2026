% ETAPE 4 : choisir une ou plusieurs simulations, puis calculer et enregistrer.
% Ne lance jamais k-Wave. Les positions sont lues dans chaque fichier.
% Executer ce script avec Run. resolution_contraste.m doit etre a cote.
dossier_code=fileparts(mfilename('fullpath'));
addpath(dossier_code);
methode='absolue'; % Seuil 0.5. 'fond' : autre convention, a comparer separement.
[fichiers,dossier]=uigetfile('*.mat','Choisir les fichiers de SIMULATION','MultiSelect','on');
if isequal(fichiers,0)
    disp('Analyse annulee.');
else
    if ischar(fichiers), fichiers={fichiers}; end
    sortie=fullfile(dossier,'analyses');
    if ~isfolder(sortie), mkdir(sortie); end
    for k=1:numel(fichiers)
        chemin=fullfile(dossier,fichiers{k});
        stats=resolution_contraste(chemin,methode);
        [~,nom]=fileparts(chemin);
        base=fullfile(sortie,['Analyse_' nom '_' methode]);
        save([base '.mat'],'stats');
        writetable(stats.par_impact,[base '_impacts.csv']);
        writetable(stats.resume,[base '_resume.csv']);
        fprintf('Analyse enregistree : %s.mat\n',base);
    end
end
