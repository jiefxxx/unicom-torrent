var server = "/ext/torrent/api"

modalTorrentReturn = function(modal ,torrent){
    var modalInstance = modal.open({
        animation: true,
        ariaLabelledBy: 'modal-title',
        ariaDescribedBy: 'modal-body',
        templateUrl: '/Torrent/modal/torrent',
        controller: 'ModalTorrentCtrl',
        controllerAs: 'pc',
        windowClass: 'show',
        backdropClass: 'show',
        size: 'lg',
        resolve: {
            torrent: function () {
                return torrent;
            }
        }
    });

    return modalInstance.result
}

app.controller('torrentTable', function($scope, $http, $uibModal, $interval){
    $scope.torrentCollection = []

    $scope.getFiles = function(){
        $("#torrent").trigger('click');
    };

    $scope.refresh = function(){
        $http.get("Torrent/api/torrent")
        .then(function (response) {
            for(var i = 0;i<response.data.length;i++){
                var ok = false;
                for(var j = 0;j<$scope.torrentCollection.length;j++){
                    if ($scope.torrentCollection[j].InfoHash == response.data[i].InfoHash){
                        Object.assign($scope.torrentCollection[j], response.data[i]);
                        ok = true;
                        break;
                    }
                }
                if(!ok){
                    $scope.torrentCollection.push(response.data[i])
                }
            }
        });
    }

    $scope.uploadFile = function(files) {
        var fd = new FormData();
        $http({
            method: 'POST',
            url: '/Torrent/api/torrent',
            data: files[0],
            headers: {'Content-Type': undefined}
        }).then(function (response) {
            modalTorrentReturn($uibModal, response.data).then(function (torrent) {
                send_activate_torrent(torrent)
            }, function (torrent){
                send_drop_torrent(torrent)
            });
        });
    };

    $scope.editFile = function() {
        var selected = getSelection($scope.torrentCollection);
        for(var i = 0;i<selected.length;i++){
            var data = {};
            $http({
                method: 'GET',
                url: 'Torrent/api/torrent/'+selected[i].InfoHash+'?full=1'
            }).then(function (response) {
                modalTorrentReturn($uibModal, response.data[0]).then(function (torrent) {
                    send_activate_torrent(torrent)
                }, function (torrent){
                    send_drop_torrent(torrent)
                });
            });
        }
    };

    $scope.pause = function(){
        var selected = getSelection($scope.torrentCollection);
        for(var i = 0;i<selected.length;i++){
            var data = {};
            data["InfoHash"] = selected[i].InfoHash
            data["Pause"] = true
            $http({
                method: 'PUT',
                url: 'Torrent/api/torrent/'+selected[i].InfoHash,
                data: data
            }).then(function (response) {
            });
        }
    }

    $scope.remove = function(){
        var selected = getSelection($scope.torrentCollection);
        for(var i = 0;i<selected.length;i++){
            var isConfirmed = confirm("Are you sure to delete this torrent ("+selected[i].Name+") ?");
            if(isConfirmed){
                send_drop_torrent(selected[i])
            }
        }
    }

    send_drop_torrent = function(torrent){
        $http({
            method: 'DELETE',
            url: 'Torrent/api/torrent/'+torrent.InfoHash
        }).then(function (response) {
            for(var j = 0;j<$scope.torrentCollection.length;j++){
                if ($scope.torrentCollection[j].InfoHash == torrent.InfoHash){
                    $scope.torrentCollection.splice(j,1)
                    break;
                }
            }
        });
    }


    send_activate_torrent = function(torrent){
        var data = {};
        data["Hooks"] = []
        for(var i = 0;i<torrent.Files.length;i++){
            if (torrent.Files[i].Hooked){
                if (torrent.Files[i].MediaInfo.MediaType == "movie"){
                    data["Hooks"].push({
                    "path":torrent.Files[i].Path,
                    "movieID": torrent.Files[i].MediaInfo.MovieID
                    })
                }
                else if (torrent.Files[i].MediaInfo.MediaType == "tv"){
                    data["Hooks"].push({
                    "path":torrent.Files[i].Path,
                    "tvID": torrent.Files[i].MediaInfo.TvID,
                    "season": torrent.Files[i].MediaInfo.Season,
                    "episode":torrent.Files[i].MediaInfo.Episode
                    })
                }
                else{
                    console.log("erreur mediainfo file hooked ", torrent.Files[i])
                }
            }
        }
        if (data["Hooks"].length == 0){
            return
        }
        $http({
            method: 'PUT',
            url: 'Torrent/api/torrent/'+torrent.InfoHash,
            data: data
        }).then(function (response) {
        });
    }

    $scope.refresh();
    $interval(function () { $scope.refresh(); }, 3000);
});

app.controller('ModalTorrentCtrl', function ($scope, $uibModal, $uibModalInstance, $http, torrent) {
    var pc = this;
    pc.torrent = torrent;

    $scope.editMovie = function(){
        selection = getSelection(pc.torrent.Files);
        getModalMovie($uibModal, selection[0]).then(function (value) {
            selection[0].MediaInfo = {"MediaType":"movie", "MovieID":parseInt(value)}
            selection[0].Hooked = true
        }, function(value){
        });
    }
    $scope.editTvShow = function(){
        selection = getSelection(pc.torrent.Files);
        getModalTvShow($uibModal, selection).then(function (files){
            for(var i=0;i<selection.length;i++){
                selection[i].MediaInfo = {"MediaType":"tv",
                "TvID":parseInt(files[i].MediaId), "Season":parseInt(files[i].Season), "Episode":parseInt(files[i].Episode)}
                selection[i].Hooked = true
            }
        }, function(value){});
    }

    pc.ok = function () {
        $uibModalInstance.close(pc.torrent);
    };

    pc.cancel = function () {
        $uibModalInstance.dismiss(pc.torrent);
      };
  });